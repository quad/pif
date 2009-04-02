import collections
import logging
import Queue
import threading

import pkg_resources

import pygtk
pygtk.require('2.0')
import gio
import gobject
import gtk
import gtk.glade

from pif.ui import OPTIONS, RE_IMAGES, common_run

LOG = logging.getLogger(__name__)

def path2uri(pathname):
    """Convert a pathname to a GIO compliant URI."""

    vfs = gio.vfs_get_local()
    f = vfs.get_file_for_path(pathname)

    return f.get_uri()

def uri2path(uri):
    """Convert a GIO compliant URI to a pathname."""

    vfs = gio.vfs_get_local()
    f = vfs.get_file_for_uri(uri)

    return f.get_path()

# Actions for EXIF orientation codes.
_exif_orient_acts = {
    1: lambda pb: pb,
    2: lambda pb: pb.flip(True),
    3: lambda pb: pb.rotate_simple(gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN),
    4: lambda pb: pb.flip(False),
    5: lambda pb: pb.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE).flip(True),
    6: lambda pb: pb.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE),
    7: lambda pb: pb.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE).flip(False),
    8: lambda pb: pb.rotate_simple(gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE),
}

def exif_orient(pixbuf):
    """Rotate a Pixbuf to its EXIF orientation."""
    o = pixbuf.get_option('orientation')
    
    if o and int(o) in _exif_orient_acts:
        return _exif_orient_acts[int(o)](pixbuf)
    else:
        return pixbuf

class Preview:
    XML = pkg_resources.resource_string(__name__, 'preview.glade')

    def __init__(self, dry_run=False):
        self.dry_run = dry_run

        self.file_index = None
        self.flickr_index = None
        self.refs = {}
        self.thumbs = {}

        self._filenames = []

        self.PIXBUF_UNKNOWN = gtk.icon_theme_get_default().load_icon('gtk-missing-image', gtk.ICON_SIZE_DIALOG, 0).scale_simple(128, 128, gtk.gdk.INTERP_BILINEAR)

        # Hookup the widgets through Glade.
        self.glade = gtk.glade.xml_new_from_buffer(self.XML, len(self.XML))
        self.glade.signal_autoconnect(self)

        # Setup the views.
        def _(view_name):
            # Setup the store.
            store = gtk.ListStore(
                gobject.TYPE_STRING,    # Filename
                gobject.TYPE_STRING,    # Basename
                gtk.gdk.Pixbuf,         # Image
            )

            # Attach the view to the store.
            view = self.glade.get_widget('view_' + view_name)
            view.set_model(store)

            # Prepare for Drag and Drop
            dnd_target = ('text/uri-list', gtk.TARGET_SAME_APP | gtk.TARGET_OTHER_WIDGET, 0)
            view.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, (dnd_target,), gtk.gdk.ACTION_MOVE)
            view.enable_model_drag_dest((dnd_target,), gtk.gdk.ACTION_DEFAULT)

            # "Empty" the view.
            self._view_init(view)

        _('ignore')
        _('new')
        _('upload')

        # Show the UI!
        self.window = self.glade.get_widget('window')
        self.window.show_all()

    def on_item_activated(self, view, path):
        """Open selected items in a view."""

        # Lookup the associated viewer for all the items.

        store = view.get_model()
        type_on_uris = collections.defaultdict(list)

        for p in view.get_selected_items():
            fn, bn, pb = store[p]

            if fn:
                type = gio.content_type_guess(fn)
                type_on_uris[type].append(path2uri(fn))

        # If the same viewer is associated to multiple types, then merge the
        # associated URIs to be launched.
        #
        # This code is convoluted because the gtk.AppInfo type is not hashable.
        # TODO: Report this as a bug in PyGTK.

        app_on_uris = []

        for type, uris in type_on_uris.items():
            app = gio.app_info_get_default_for_type(type, True)
            l_apps = map(lambda x: x[0], app_on_uris)

            if app in l_apps:
                idx = l_apps.index(app)

                app_on_uris[idx][1].extend(uris)
            else:
                app_on_uris.append((app, uris))

        # Launch the associated viewers for all items.

        for app, uris in app_on_uris:
            if app:
                if not app.launch_uris(uris):
                    self.alert("Couldn't launch %s." % app.get_name())
            else:
                self.alert("No associated viewer for type '%s'." % type)

    def on_view_drag_data_get(self, view, context, selection, info, timestamp):
        """Provide the file URIs used for items in drag and drop."""

        store = view.get_model()

        selection.set_uris(
            [path2uri(store[p][0]) for p in view.get_selected_items()]
        )

    def on_view_drag_data_received(self, view, context, x, y, selection, info, timestamp):
        """Add items from another view via drag and drop."""

        store = view.get_model()

        for uri in selection.get_uris():
            self._view_add(view, uri2path(uri))

        if context.action & gtk.gdk.ACTION_MOVE:
            context.finish(True, True, timestamp)

    def on_view_drag_data_delete(self, view, context):
        """Delete items added to another view via drag and drop."""

        store = view.get_model()

        # Use TreeRowReferences to maintain reference intergrity.
        refs = [gtk.TreeRowReference(store, p) for p in view.get_selected_items()]

        for r in refs:
            p = r.get_path()

            if p:
                self._view_remove(view, p)

    def _view_init(self, view):
        """Initialize a view."""

        # Make the view appear empty.
        view.props.can_focus = False
        view.props.pixbuf_column = -1
        view.props.text_column = -1

        # Clear out the view's store.
        store = view.get_model()
        store.clear()

        # Insert a stub entry in the store, so DnD will still respond.
        # TODO: Bug GTK about this problem.
        store.append((None, None, None))

    def _view_is_active(self, view):
        """Return if a view is active."""

        return view.props.can_focus

    def _view_add(self, view, filename):
        """Add an image to a view."""

        store = view.get_model()

        # If the view is stubbed, then reactivate it.
        if not self._view_is_active(view):
            store.clear()
            view.props.can_focus = True
            view.props.pixbuf_column = 2
            view.props.text_column = 1

        # Load the file into the store.
        iter = store.append((
            filename,
            gobject.filename_display_basename(filename),
            self.thumbs.get(filename, self.PIXBUF_UNKNOWN)
        ))
        self.refs[filename] = gtk.TreeRowReference(store, store.get_path(iter))

    def _view_remove(self, view, path):
        """Remove an image from a view."""

        store = view.get_model()

        fn, bn, pb_old = store[path]
        del store[path]

        # If the store is empty, then add a stub entry.
        if len(store) == 0:
            self._view_init(view)

    def request_images_cb(self, callback):
        """Request a folder of images to operate upon."""

        fcd = gtk.FileChooserDialog(
            title='Select folder(s) to scan for photos...',
            parent=self.window,
            action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                     gtk.STOCK_OPEN, gtk.RESPONSE_OK),
        )
        fcd.props.local_only = True
        fcd.props.select_multiple = True

        filter = gtk.FileFilter()
        filter.set_name('Images')
        filter.add_custom(
            gtk.FILE_FILTER_FILENAME,
            lambda info: RE_IMAGES.match(info[0])
        )
        fcd.add_filter(filter)

        gtk.gdk.threads_enter()
        resp = fcd.run()
        gtk.gdk.threads_leave()

        # We only cancel if specifically requested.
        if resp == gtk.RESPONSE_OK:
            fns = fcd.get_filenames()

            fcd.destroy()

            callback(fns)
        else:
            self.on_close(None)

    def flickr_proxy_tcb(self):
        """Inform about waiting for Flickr."""

        gtk.gdk.threads_enter()
        self.set_status('Waiting for authorization from Flickr...')
        gtk.gdk.threads_leave()

    def flickr_progress_cb(self, state, meta):
        """Update the progress bar from the Flickr update."""

        msgs = {
            'update': 'Loading updates from Flickr...',
            'index': 'Indexing photos on Flickr...',
        }

        a, b = meta
        self.set_status(
            msgs[state],
            (float(a) / float(b))
        )

    def flickr_indexes_cb(self, indexes):
        """Register file and Flickr indexes."""

        self.file_index, self.flickr_index = indexes

        if not self.flickr_index.proxy:
            self.alert('Couldn\'t connect to Flickr.')

    def loading_images_cb(self, queue):
        """Load images into the new view."""

        try:
            fn = queue.get(block=False)
        except Queue.Empty:
            return True

        if fn:
            self._filenames.append(fn)
            queue.task_done()

        count = len(self._filenames)

        if fn:
            self.set_status("%u images scanned" % count)
            self.window.props.title = "%u images (scanning) - pif" % count

            return True
        else:
            view = self.glade.get_widget('view_new')
            for fn in self._filenames:
                self._view_add(view, fn)

            queue.task_done()

            self.set_sensitive(True)
            self.set_status(None)
            self.window.props.title = "%u images - pif" % count

    def loading_thumbs_cb(self, queue):
        """Load thumbnails into the appropriate view."""

        try:
            results = queue.get(block=False)
        except Queue.Empty:
            return True

        queue.task_done()

        if results:
            fn, pb_new = results

            self.thumbs[fn] = pb_new

            if self.refs.has_key(fn):
                ref = self.refs[fn]

                p = ref.get_path()
                store = ref.get_model()

                if p and store:
                    fn, bn, pb_old = store[p]
                    store[p] = (fn, bn, pb_new)

                self.set_status(
                    "%u of %u thumbnails loaded" % (len(self.thumbs), len(self.refs)),
                    (float(len(self.thumbs)) / float(len(self.refs)))
                )
            else:
                LOG.critical("Icon reference miss on %s (threading issue)" % fn)

            return True

    def loading_done_cb(self):
        self.set_status(None)

    def upload_progress_cb(self, count, total):
        """Update the progress bar on the Flickr upload."""

        self.set_status(
            "%u of %u photos uploaded to Flickr" % (int(count), total),
            float(count) / float(total)
        )

    def upload_done_cb(self, success, url):
        """Open the uploaded photos redirection website."""

        if url:
            gtk.show_uri(
                gtk.gdk.screen_get_default(),
                url,
                gtk.get_current_event_time()
            )

        if success:
            self.on_close(None)
        else:
            # TODO: A whole lot. Figure out what was uploaded, and remember
            # that. Then re-init the whole program, resync to Flickr, and
            # re-scan for photos. After the re-scan, automatically move the
            # previous selections over into the Upload view.
            self.alert('Upload failed!', exit_on_close=True)

    def set_status(self, status, fraction=None):
        """Update the progress bar."""

        progress = self.glade.get_widget('progressbar')

        if status:
            progress.props.text = status

            if fraction:
                progress.props.fraction = fraction
            else:
                progress.pulse()
        else:
            progress.props.fraction = 0.0
            progress.props.text = ''

    def set_sensitive(self, sensitivity):
        """Update the sensitivity of the window."""

        buttons = [self.glade.get_widget('button_ok'), ]
        views = map(self.glade.get_widget, ('view_ignore', 'view_new', 'view_upload'))

        map(lambda v: v.set_sensitive(sensitivity), views + buttons)

    def alert(self, message, exit_on_close=False):
        """Display an alert in the top of window."""

        LOG.warn(message)

        # Build the alert pane.

        text = gtk.Label(message)

        img = gtk.Image()
        img.set_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)

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
                self.on_close(widget)

        close.connect('clicked', lambda b: _(ebox))
        ebox.connect('button-release-event', lambda w, e: _(w))
        ebox.connect('enter-notify-event', lambda w, e: frame.set_shadow_type(gtk.SHADOW_IN))
        ebox.connect('leave-notify-event', lambda w, e: frame.set_shadow_type(gtk.SHADOW_OUT))

        vbox.show_all()

    def on_ok(self, button):
        """Process the categorized images."""

        self.set_sensitive(False)

        # Mark images as "already uploaded."

        ignores = [fn
                   for fn, bn, pb in self.glade.get_widget('view_ignore').get_model()
                   if fn]

        if not self.dry_run:
            for fn in ignores:
                self.flickr_index.add(self.file_index[fn], None)

        # Upload the images!

        if self.dry_run:
            self.on_close(None)
        else:
            uploads = [fn
                       for fn, bn, pb in self.glade.get_widget('view_upload').get_model()
                       if fn]

            t_upload = FlickrUploader(
                self.flickr_index,
                progress_callback=idle_proxy(self.upload_progress_cb),
                done_callback=idle_proxy(self.upload_done_cb)
            )
            t_upload.start(uploads)

    def on_close(self, widget, user_data=None):
        """Quit!"""

        # Alert if there are unsaved changes.

        views = map(self.glade.get_widget, ('view_ignore', 'view_upload'))
        changed = map(lambda v: v.props.sensitive and self._view_is_active(v), views)

        if True in changed:
            md = gtk.MessageDialog(
                parent=self.window,
                flags=gtk.DIALOG_MODAL,
                type=gtk.MESSAGE_WARNING,
                buttons=gtk.BUTTONS_OK_CANCEL,
                message_format='There are unsaved changes.\n\nAre you sure you want to exit?'
            )

            resp = md.run()

            # We only cancel if specifically requested.
            if resp != gtk.RESPONSE_OK:
                md.destroy()
                return True

        # Save changes!

        if self.file_index:
            self.file_index.sync()

        if not self.dry_run and self.flickr_index:
            self.flickr_index.sync()

        gtk.main_quit()

class FlickrUpdater(threading.Thread):
    """Worker thread for updating from Flickr."""

    def __init__(self, proxy_callback=None, progress_callback=None, done_callback=None):
        threading.Thread.__init__(self)

        self.proxy_callback = proxy_callback
        self.progress_callback = progress_callback
        self.done_callback = done_callback

        self.setDaemon(True)

    def run(self):
        if self.proxy_callback:
            self.proxy_callback()

        indexes, filenames = common_run(self.opts, self.proxy_callback, self.progress_callback)
        self.file_index, self.flickr_index = indexes

        if self.done_callback:
            self.done_callback(indexes, filenames)

    def start(self, opts):
        self.opts = opts

        threading.Thread.start(self)

class ImageLoader(threading.Thread):
    """Worker thread for scanning the filesystem for images."""

    def __init__(self, loading_callback=None, done_callback=None):
        threading.Thread.__init__(self)

        self.loading_callback = loading_callback
        self.done_callback = done_callback

        self.setDaemon(True)

    def run(self):
        queue = Queue.Queue()

        if self.loading_callback:
            self.loading_callback(queue)

        fns = []
        for fn in self.filenames:
            fns.append(fn)
            queue.put(fn)
        queue.put(None)

        queue.join()

        if self.done_callback:
            self.done_callback(fns)

    def start(self, filenames):
        self.filenames = filenames

        threading.Thread.start(self)

class ThumbLoader(threading.Thread):
    """Worker thread for loading thumbnails."""

    def __init__(self, loading_callback=None, done_callback=None):
        threading.Thread.__init__(self)

        self.loading_callback = loading_callback
        self.done_callback = done_callback

        self.setDaemon(True)

    def run(self):
        queue = Queue.Queue()

        if self.loading_callback:
            self.loading_callback(queue)

        for fn in self.filenames:
            queue.put((
                fn,
                exif_orient(gtk.gdk.pixbuf_new_from_file_at_size(fn, 128, 128))
            ))
        queue.put(None)

        queue.join()

        if self.done_callback:
            self.done_callback()

    def start(self, filenames):
        self.filenames = filenames

        threading.Thread.start(self)

class FlickrUploader(threading.Thread):
    """Worker thread for uploading to Flickr."""

    def __init__(self, flickr_index, progress_callback=None, done_callback=None):
        threading.Thread.__init__(self)

        self.flickr_index = flickr_index
        self.progress_callback = progress_callback
        self.done_callback = done_callback

        self.setDaemon(True)

    def run(self):
        def _upload(fns):
            for n, fn in enumerate(fns):
                if self.progress_callback:
                    def _(progress, done):
                        if done: p = n + 1
                        else: p = n + (progress / 100)
                        self.progress_callback(p, len(self.filenames))
                else:
                    _ = None

                # TODO: This will probably throw an exception in case of a serious error.
                # We should track those down, and handle them appropriately.
                yield self.flickr_index.upload(filename=fn, callback=_)

        ids = []
        for resp in _upload(self.filenames):
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

        url = 'http://www.flickr.com/tools/uploader_edit.gne?ids=' + ','.join(ids) if ids else None

        if self.done_callback:
            self.done_callback(len(self.filenames) == len(ids), url)

    def start(self, filenames):
        self.filenames = filenames

        threading.Thread.start(self)

def idle_proxy(func):
    """Thunk a function into the gobject event loop."""

    def _(proxy):
        func, args, kwargs = proxy
        return func(*args, **kwargs)

    return lambda *args, **kwargs: gobject.idle_add(_, (func, args, kwargs))

def run():
    # Ensure we're graphical.
    if not gtk.gdk.get_display():
        OPTIONS.error('Cannot open display.')

    # Parse the command-line.
    opts = OPTIONS.parse_args()
    options, args = opts

    # Prepare the GUI and worker threads.

    gtk.gdk.threads_init()
    preview = Preview(options.dry_run)

    t_thumb = ThumbLoader(
        loading_callback=idle_proxy(preview.loading_thumbs_cb),
        done_callback=idle_proxy(preview.loading_done_cb)
    )
    t_image = ImageLoader(
        loading_callback=idle_proxy(preview.loading_images_cb),
        done_callback=t_thumb.start
    )
    t_flickr = FlickrUpdater(
        proxy_callback=preview.flickr_proxy_tcb,
        progress_callback=idle_proxy(preview.flickr_progress_cb),
        done_callback=lambda indexes, filenames: idle_proxy(preview.flickr_indexes_cb(indexes)) and t_image.start(filenames)
    )

    # Let the user select files if they weren't specified.
    if args:
        t_flickr.start(opts)
    else:
        gobject.idle_add(preview.request_images_cb, lambda fns: t_flickr.start((options, fns)))

    gtk.main()
