import logging
import os.path
import Queue
import threading

import pkg_resources

import pygtk
pygtk.require('2.0')
import gio
import gobject
import gtk
import gtk.glade

from pif.ui import OPTIONS, common_run, upload_images

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

class ThumbnailLoader(dict):
    def __init__(self, notify_callback):
        self.callback = notify_callback
        self.queue = Queue.Queue()

        self.thread = threading.Thread(target=self._load_thumbs)
        self.thread.setDaemon(True)

        self.start = self.thread.start

    def stop(self):
        # Drain the thumbnail queue, and cancel it.
        try:
            while self.queue.get(block=False):
                self.queue.task_done()
        except Queue.Empty:
            self.queue.put((None, None))
            if self.thread.isAlive():
                self.queue.join()

    def request(self, filename, user_data):
        self.queue.put(
            (filename, user_data)
        )

    def _load_thumbs(self):
        while True:
            fn, user_data = self.queue.get()

            if not fn:
                self.queue.task_done()
                break

            if not self.has_key(fn):
                self[fn] = exif_orient(
                    gtk.gdk.pixbuf_new_from_file_at_size(fn, 128, 128)
                )

            self.callback(fn, user_data)
            self.queue.task_done()

class Preview:
    XML = pkg_resources.resource_string(__name__, 'preview.glade')
    PIXBUF_UNKNOWN = gtk.icon_theme_get_default().load_icon('gtk-missing-image', gtk.ICON_SIZE_DIALOG, 0).scale_simple(128, 128, gtk.gdk.INTERP_BILINEAR)

    def __init__(self, filenames):
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
            store.set_sort_column_id(0, gtk.SORT_ASCENDING)

            # Attach the view to the store.
            view = self.glade.get_widget('view_' + view_name)
            view.set_model(store)

            # Prepare for Drag and Drop

            dnd_target = ('text/uri-list', gtk.TARGET_SAME_APP | gtk.TARGET_OTHER_WIDGET, 0)

            view.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, (dnd_target,), gtk.gdk.ACTION_MOVE)
            view.enable_model_drag_dest((dnd_target,), gtk.gdk.ACTION_DEFAULT)

            self._view_init(view)

            return view

        view_ignore = _('ignore')
        view_new = _('new')
        view_upload = _('upload')

        # Preload the new view with stub images.
        self.progress = self.glade.get_widget('progressbar')
        gobject.idle_add(self._load_images(view_new, filenames).next)

        self.window = self.glade.get_widget('window')
        self.window.show_all()

    def on_item_activated(self, view, path):
        """Open selected images."""
        store = view.get_model()

        for p in view.get_selected_items():
            fn, bn, pb = store[p]

            gtk.show_uri(
                gtk.gdk.screen_get_default(),
                path2uri(fn),
                gtk.get_current_event_time()
            )

    def on_view_drag_data_get(self, view, context, selection, info, timestamp):
        store = view.get_model()

        selection.set_uris(
            [path2uri(store[p][0]) for p in view.get_selected_items()]
        )

    def on_view_drag_data_received(self, view, context, x, y, selection, info, timestamp):
        store = view.get_model()

        for uri in selection.get_uris():
            self._view_add(view, uri2path(uri))

        if context.action & gtk.gdk.ACTION_MOVE:
            context.finish(True, True, timestamp)

    def on_view_drag_data_delete(self, view, context):
        # Delete using TreeRowReferences to maintain reference intergrity.

        store = view.get_model()
        refs = [gtk.TreeRowReference(store, p) for p in view.get_selected_items()]

        for r in refs:
            p = r.get_path()

            if p:
                self._view_remove(view, p)

    def _view_init(self, view):
        # Detach the view's columns.
        view.props.text_column = -1
        view.props.pixbuf_column = -1

        # Clear out the view's store.
        store = view.get_model()
        store.clear()

        # Insert a stub entry in the store, so DnD will still respond.
        # TODO: Bug GTK about this problem.
        store.append((None, None, None))

    def _view_add(self, view, filename):
        store = view.get_model()
        
        # If the view is stubbed, then reactivate it.
        if view.get_text_column() == -1:
            store.clear()
            view.props.text_column = 1
            view.props.pixbuf_column = 2

        # Try to find a cached thumbnail.
        if self.thumb_loader.has_key(filename):
            pb = self.thumb_loader[filename]
        else:
            pb = self.PIXBUF_UNKNOWN

        # Load the file into the store.
        iter = store.append((
            filename,
            os.path.basename(filename),
            pb
        ))

        if pb == self.PIXBUF_UNKNOWN:
            self.thumb_loader.request(filename, gtk.TreeRowReference(store, store.get_path(iter)))

    def _view_remove(self, view, path):
        store = view.get_model()
        del store[path]

        # If the store is empty, then add a stub entry.
        if len(store) == 0:
            self._view_init(view)

    def _load_images(self, view, filenames):
        # Warm up the thumbnail loader.
        self.thumb_queue = Queue.Queue()
        self.thumb_loader = ThumbnailLoader(lambda fn, user_data: self.thumb_queue.put(user_data))

        # Load the stubs (this takes time, so disable the view).
        view.set_sensitive(False)
        self.progress.props.text = 'Scanning...'

        for fn in filenames:
            self._view_add(view, fn)

            num_of_images = len(view.get_model())

            self.progress.pulse()
            self.progress.props.text = "%u images scanned" % num_of_images
            self.window.props.title = "%u images (scanning) - pif" % num_of_images

            yield True

        self.window.props.title = "%u images - pif" % num_of_images
        view.set_sensitive(True)

        # Load the thumbnails.
        gobject.idle_add(self.thumb_loader.start)
        gobject.idle_add(self._display_thumbs(num_of_images).next)

    def _display_thumbs(self, num_of_images):
        cache = self.thumb_loader
        queue = self.thumb_queue
        count = 0

        while count < num_of_images:
            try:
                ref = queue.get(block=False)

                store = ref.get_model()
                p = ref.get_path()

                if p:
                    fn, bn, pb = store[p]
                    store[p] = (fn, bn, cache[fn])

                count += 1
                self.progress.props.fraction = float(count) / num_of_images
                self.progress.props.text = "%u of %u images loaded" % (count, num_of_images)

                queue.task_done()
            except Queue.Empty:
                pass

            yield True

        self.progress.props.fraction = 0.0
        self.progress.props.text = ''

    def on_close(self, *args):
        self.upload = [fn
                       for fn, bn, pb in self.glade.get_widget('view_upload').get_model()
                       if fn]
        self.ignore = [fn
                       for fn, bn, pb in self.glade.get_widget('view_ignore').get_model()
                     if fn]

        self.thumb_loader.stop()
        gtk.main_quit()

def proxy_callback():
    LOG.info('Waiting for authorization from Flickr...')
    time.sleep(5)

def run():
    options, args = OPTIONS.parse_args()
    indexes, images = common_run((options, args), proxy_callback)
    file_index, flickr_index = indexes

    gtk.gdk.threads_init()
    preview = Preview(images)
    gtk.main()

    LOG.debug("Upload: %s" % preview.upload)
    LOG.debug("Ignore: %s" % preview.ignore)

    file_index.sync()
    flickr_index.sync()
