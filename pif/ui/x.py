import collections
import logging
import os
import Queue
import sys
import threading

import pkg_resources

from decorator import decorator

import pygtk
pygtk.require('2.0')
import gio
import gnome.ui
import gobject
import gtk
import gtk.glade

from pif.ui.shell import Shell
from pif.flickr import FlickrError

LOG = logging.getLogger(__name__)


def thunk(function):
    """Enqueue the method-call into the GObject mainloop."""

    def _(func, *args, **kwargs):
        gobject.idle_add(lambda: func(*args, **kwargs))

    return decorator(_, function)


def thread(function):
    """Spawn a thread for the method-call."""

    def _worker(func, *args, **kwargs):
        def _wrapper():
            try:
                func(*args, **kwargs)
            except SystemExit:
                raise
            except:
                def _(exc_info):
                    type, value, traceback = exc_info
                    raise type, value, traceback
                thunk(_)(sys.exc_info())

        t = threading.Thread(target=_wrapper)
        t.setDaemon(True)
        t.start()

        return t

    return decorator(_worker, function)


class FolderScanDialog(gtk.FileChooserDialog):
    """A chooser for photo folders."""

    def __init__(self, filter_re, parent=None):
        # TODO: Why is "ACTION_SELECT_FOLDER" a total pack of fucking lies? In
        # that it will create a directory if a non-existent one is supplied.
        gtk.FileChooserDialog.__init__(
            self,
            title='Select folder(s) to scan for photos...',
            parent=parent.window,
            action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                     gtk.STOCK_OPEN, gtk.RESPONSE_OK),
        )

        self.props.local_only = True
        self.props.select_multiple = True

        filter = gtk.FileFilter()
        filter.set_name('Images')
        filter.add_custom(
            gtk.FILE_FILTER_FILENAME,
            lambda info: filter_re.match(info[0]))
        self.add_filter(filter)

    def run(self):
        resp = gtk.FileChooserDialog.run(self)

        if resp == gtk.RESPONSE_OK:
            return self.get_filenames()


class PreviewWindow(gobject.GObject):
    """A preview window."""

    __gsignals__ = {
        'close': (gobject.gobject.SIGNAL_RUN_LAST,
                  gobject.TYPE_BOOLEAN, ()),
        'upload': (gobject.gobject.SIGNAL_RUN_LAST,
                  gobject.TYPE_BOOLEAN, ())}

    XML = pkg_resources.resource_string(__name__, 'preview.glade')

    def __init__(self):
        self.__gobject_init__()
        self._init_gtk()

    def _init_gtk(self):
        self.glade = gtk.glade.xml_new_from_buffer(self.XML, len(self.XML))

        # Hookup the preview window.
        self.window = self.glade.get_widget('window')
        self.window.connect('delete_event', self.on_close)

        cancel = self.glade.get_widget('button_cancel')
        cancel.connect('clicked', self.on_close)

        ok = self.glade.get_widget('button_ok')
        ok.connect('clicked', self.on_ok)

        # Hookup the views.
        self.views = {
            'ignore': self.glade.get_widget('view_ignore'),
            'new': self.glade.get_widget('view_new'),
            'upload': self.glade.get_widget('view_upload'),
        }

        for v in self.views.values():
            v.connect('item_activated', self.on_item_activated)
            v.connect('key_release_event', self.on_view_key)

        self.window.show_all()

    def set_status(self, status='', fraction=0.0):
        """Update the progress bar."""

        progress = self.glade.get_widget('progressbar')

        if status:
            if status == progress.props.text:
                if fraction == progress.props.fraction:
                    return
            else:
                LOG.info(status)

        progress.props.text = status
        progress.props.fraction = fraction

    def set_sensitive(self, sensitivity):
        """Update the sensitivity of the window."""

        buttons = [self.glade.get_widget('button_ok'), ]

        map(lambda v: v.set_sensitive(sensitivity),
            self.views.values() + buttons)

    def alert(self, message, exit_on_close=False):
        """Display an alert in the top of window."""

        if exit_on_close:
            LOG.fatal(message)
        else:
            LOG.warn(message)

        # Build the alert pane.

        text = gtk.Label(message)

        img = gtk.image_new_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)

        close = gtk.Button()
        close.set_image(img)
        close.set_relief(gtk.RELIEF_NONE)

        hbox = gtk.HBox()
        hbox.pack_start(text)
        hbox.pack_start(close, expand=False)

        frame = gtk.Frame()
        frame.add(hbox)
        frame.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse('yellow'))
        frame.set_shadow_type(gtk.SHADOW_OUT)

        ebox = gtk.EventBox()
        ebox.add(frame)

        vbox = self.glade.get_widget('vbox')
        vbox.pack_start(ebox, expand=False)
        vbox.reorder_child(ebox, 0)

        # Connect events for destroying the pane and exiting the application.
        def _(widget):
            widget.destroy()

            if exit_on_close:
                self.emit('close')

        close.connect('clicked', lambda b: _(ebox))
        ebox.connect('button-release-event', lambda w, e: _(w))
        ebox.connect('enter-notify-event',
                     lambda w, e: frame.set_shadow_type(gtk.SHADOW_IN))
        ebox.connect('leave-notify-event',
                     lambda w, e: frame.set_shadow_type(gtk.SHADOW_OUT))

        vbox.show_all()

    def on_close(self, widget, user_data=None):
        """Quit, but warn if there are unsaved changes."""

        views = map(self.glade.get_widget, ('view_ignore', 'view_upload'))
        # TODO: Are these the appropriate boolean checks?
        changed = map(lambda v: v.props.sensitive and v.props.can_focus, views)

        if True in changed:
            md = gtk.MessageDialog(
                parent=self.window,
                flags=gtk.DIALOG_MODAL,
                type=gtk.MESSAGE_WARNING,
                buttons=gtk.BUTTONS_OK_CANCEL,
                message_format='There are unsaved changes.\n\n' \
                'Are you sure you want to exit?')

            resp = md.run()

            # We only cancel if specifically requested.
            if resp != gtk.RESPONSE_OK:
                md.destroy()
                return True

        return self.emit('close')

    def on_view_key(self, source_view, event):
        """Move items between views via key-press."""

        # Determine the source and destination stores.
        _ = lambda n: self.glade.get_widget('view_' + n)
        dests = {
            gtk.gdk.keyval_from_name('I'): _('ignore'),
            gtk.gdk.keyval_from_name('N'): _('new'),
            gtk.gdk.keyval_from_name('U'): _('upload'),
        }
        dest_view = dests.get(gtk.gdk.keyval_to_upper(event.keyval), None)

        if dest_view == None or dest_view == source_view:
            return

        dest_store = dest_view.get_model()
        source_store = source_view.get_model()

        # Use TreeRowReferences to maintain reference intergrity.
        selected = source_view.get_selected_items()
        refs = [gtk.TreeRowReference(source_store, p) for p in selected]

        # Save the selection path.
        saved_p = min(selected)

        for r in reversed(refs):
            p = r.get_path()

            dest_store.add(source_store[p].uri)
            del source_store[p]

        # Restore the selection path.
        source_view.select_path(saved_p)

    def on_item_activated(self, view, path):
        """Open selected items in a view."""

        store = view.get_model()

        # If the same viewer is associated to multiple types, then merge the
        # associated URIs to be launched.
        #
        # This code is convoluted because the gtk.AppInfo type is not hashable.
        app_on_uris = []

        for p in view.get_selected_items():
            uri = store[p].uri

            mime = gio.content_type_guess(uri)
            app = gio.app_info_get_default_for_type(mime, True)

            l_apps = map(lambda x: x[0], app_on_uris)

            if app in l_apps:
                idx = l_apps.index(app)
                app_on_uris[idx][1].add(mime)
                app_on_uris[idx][2].append(uri)
            else:
                app_on_uris.append((app, set(mime), [uri,]))

        # Launch the associated viewers for all items.
        for app, mime, uris in app_on_uris:
            if app:
                if not app.launch_uris(uris):
                    self.alert("Couldn't launch %s." % app.get_name())
            else:
                self.alert("No associated viewer for type '%s'." % mime)

    def on_ok(self, button):
        """Process the categorized images."""

        self.set_sensitive(False)

        return self.emit('upload')


class ImageStore(gtk.ListStore):
    PIXBUF_UNKNOWN = gtk.gdk.pixbuf_new_from_file_at_scale(
        gtk.icon_theme_get_default().lookup_icon('image-loading',
                                                 gtk.ICON_SIZE_DIALOG, 0).get_filename(),
        -1, 128,
        True)

    Image = collections.namedtuple('Image', 'uri basename pixbuf')

    __thumbnail_queue__ = Queue.Queue()
    __thumbnail_cache__ = {}
    __thumbnail_thread__ = None

    def __init__(self, view_widget):
        gtk.ListStore.__init__(
            self,
            gobject.TYPE_STRING,    # URI
            gobject.TYPE_STRING,    # Basename
            gtk.gdk.Pixbuf,         # Image
        )

        # Start the thumbnailer.
        if not type(self).__thumbnail_thread__:
            type(self).__thumbnail_thread__ = self._thumbnail_wt()

        # Attach the view to the store.
        view_widget.props.can_focus = True
        view_widget.props.pixbuf_column = 2
        view_widget.props.text_column = 1
        view_widget.set_model(self)

    def __getitem__(self, key):
        return self.Image(*gtk.ListStore.__getitem__(self, key))

    def __iter__(self):
        return (self.Image(*v) for v in gtk.ListStore.__iter__(self))

    @thread
    def _thumbnail_wt(self):
        thumber = gnome.ui.ThumbnailFactory(gnome.ui.THUMBNAIL_SIZE_NORMAL)

        while True:
            uri, ref = type(self).__thumbnail_queue__.get()

            mime = gio.content_type_guess(uri)
            mtime = int(gio.File(uri) \
                        .query_info(gio.FILE_ATTRIBUTE_TIME_MODIFIED) \
                        .get_modification_time())

            if (uri, mtime) in type(self).__thumbnail_cache__:
                t = type(self).__thumbnail_cache__[(uri, mtime)]
            else:
                t_uri = thumber.lookup(uri, mtime)

                if t_uri:
                    t = gtk.gdk.pixbuf_new_from_file(t_uri)
                elif thumber.can_thumbnail(uri, mime, mtime):
                    t = thumber.generate_thumbnail(uri, mime)
                    if t != None:
                        thumber.save_thumbnail(t, uri, mtime)

                type(self).__thumbnail_cache__[(uri, mtime)] = t

            if t != None:
                self._new_thumbnail(ref, t)

    @thunk
    def _new_thumbnail(self, ref, thumbnail):
        p = ref.get_path()
        store = ref.get_model()

        if p and store:
            store[p] = store[p]._replace(pixbuf=thumbnail)

    def add(self, uri):
        i = self.Image(uri=uri,
                       basename=gio.File(uri) \
                                .query_info(gio.FILE_ATTRIBUTE_STANDARD_DISPLAY_NAME) \
                                .get_display_name(),
                       pixbuf=self.PIXBUF_UNKNOWN)
        iter = self.append(i)

        # Queue the image to be thumbnailed.
        ref = gtk.TreeRowReference(self, self.get_path(iter))
        type(self).__thumbnail_queue__.put_nowait((uri, ref))


class GTKShell(Shell):
    def __init__(self):
        Shell.__init__(self)

        self.preview_window = PreviewWindow()
        self.preview_window.connect('upload', self.on_upload)
        self.preview_window.connect('close', self.on_close)

        self.stores = {
            'ignore': ImageStore(self.preview_window.views['ignore']),
            'new': ImageStore(self.preview_window.views['new']),
            'upload': ImageStore(self.preview_window.views['upload']),
        }

        self.index = None

    def run(self):
        if not gtk.gdk.get_display():
            self.option_parser.error('Cannot open the display.')

        gobject.timeout_add_seconds(0, self.start)
        gtk.main()

    def start(self):
        # Show a scan dialog if nothing is specified on the command-line.
        if not self.remain_args:
            fsd = FolderScanDialog(self.RE_IMAGES, self.preview_window)
            fns = fsd.run()

            if fns:
                self.remain_args.extend(fns)
            else:
                self.preview_window.emit('close')

            fsd.destroy()

        self._update_flickr_wt()

    @thread
    def _update_flickr_wt(self):
        try:
            index = self.make_index(self.flickr_proxy_cb, self.flickr_progress_cb)
        except IOError:
            index = None

        self.flickr_done_cb(index)

    @thunk
    def flickr_proxy_cb(self, proxy, perms, token, frob):
        self.preview_window.set_status('Waiting for authorization from Flickr...')

    @thunk
    def flickr_progress_cb(self, state, meta):
        msgs = {
            'photos': 'Loading updates from Flickr...',
            'hashes': 'Indexing photos on Flickr...',
        }

        a, b = map(float, meta)
        self.preview_window.set_status(msgs[state], a / b)

    @thunk
    def flickr_done_cb(self, index):
        if index:
            self.index = index
        else:
            self.preview_window.set_status(None)
            return self.preview_window.alert("Couldn't connect to Flickr.",
                                             exit_on_close=True)

        self._scan_files_wt()

    @thread
    def _scan_files_wt(self):
        for fn in self.filenames:
            if self.index.type(fn) == 'new':
                self.file_new_cb(fn)

        self.files_done_cb()

    @thunk
    def file_new_cb(self, filename):
        self.stores['new'].add(gio.File(filename).get_uri())
        self.preview_window.set_status("%u new images scanned" % len(self.stores['new']))

    @thunk
    def files_done_cb(self):
        self.preview_window.set_status(None)
        self.preview_window.set_sensitive(True)

    def on_upload(self, preview):
        for i in self.stores['ignore']:
            fn = gio.File(i.uri).get_path()

            self.index.ignore(fn)

        uploads = [gio.File(i.uri).get_path() for i in self.stores['upload']]
        self.upload(uploads)

    @thread
    def upload(self, filenames):
        ids = []

        def _upload(fns):
            for n, fn in enumerate(fns):
                def _(progress, done):
                    if done:
                        p = n + 1
                    else:
                        p = n + (progress / 100)
                    self.upload_progress_cb(p, len(filenames))

                yield self.index.upload(fn, callback=_)

        try:
            for resp in _upload(filenames):
                if resp is not None:
                    photo_id = resp.find('photoid')

                    if photo_id is not None:    # Ugly because the photoid element is a boolean False.
                        ids.append(photo_id.text)
                    else:
                        LOG.debug('No photo_id in the enclosed response.')
                        break
                else:
                    LOG.debug('No response from the upload proxy.')
                    break
        except (FlickrError, IOError):
            LOG.exception('Upload failed.')

        url = 'http://www.flickr.com/tools/uploader_edit.gne?ids=' + ','.join(ids) if ids else None

        self.upload_done_cb(len(filenames) == len(ids), url)

    @thunk
    def upload_progress_cb(self, count, total):
        """Update the progress bar on the Flickr upload."""

        self.preview_window.set_status(
            "%u of %u photos uploaded to Flickr" % (int(count), total),
            float(count) / float(total))

    @thunk
    def upload_done_cb(self, success, url):
        """Open the uploaded photos redirection website."""

        if url:
            gtk.show_uri(
                gtk.gdk.screen_get_default(),
                url,
                gtk.get_current_event_time())

        if success:
            self.preview_window.emit('close')
        else:
            self.preview_window.alert('Upload to Flickr failed!',
                                      exit_on_close=True)

    def on_close(self, preview):
        # TODO: Really should make more stringent checks...
        if self.index:
            self.index.sync()

        gtk.main_quit()


def run():
    gobject.threads_init()

    GTKShell().run()
