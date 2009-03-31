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
    PIXBUF_UNKNOWN = gtk.icon_theme_get_default().load_icon('gtk-missing-image', gtk.ICON_SIZE_DIALOG, 0).scale_simple(128, 128, gtk.gdk.INTERP_BILINEAR)

    def __init__(self):
        self.refs = {}
        self.thumbs = {}

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

        store = view.get_model()

        for p in view.get_selected_items():
            fn, bn, pb = store[p]

            if fn:
                gtk.show_uri(
                    gtk.gdk.screen_get_default(),
                    path2uri(fn),
                    gtk.get_current_event_time()
                )

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

    def _view_add(self, view, filename):
        """Add an image to a view."""

        store = view.get_model()
        
        # If the view is stubbed, then reactivate it.
        if view.get_text_column() == -1:
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

    def loading_images_cb(self, queue):
        """Load images into the new view."""

        try:
            fn = queue.get(block=False)
        except Queue.Empty:
            return True

        queue.task_done()

        view = self.glade.get_widget('view_new')
        count = len(view.get_model())

        if fn:
            self._view_add(view, fn)

            self.set_status("%u images scanned" % count)
            self.window.props.title = "%u images (scanning) - pif" % count

            return True
        else:
            self.glade.get_widget('button_ok').set_sensitive(True)
            self.set_status(None)
            self.window.props.title = "%u images - pif" % count

            views = map(self.glade.get_widget, ('view_ignore', 'view_new', 'view_upload'))
            map(lambda v: v.set_sensitive(True), views)

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

    def on_ok(self, button):
        upload = [fn
                  for fn, bn, pb in self.glade.get_widget('view_upload').get_model()
                  if fn]
        ignore = [fn
                  for fn, bn, pb in self.glade.get_widget('view_ignore').get_model()
                  if fn]

        LOG.debug("Upload: %s" % upload)
        LOG.debug("Ignore: %s" % ignore)

    on_close = gtk.main_quit

class FlickrUpdater(threading.Thread):
    """Worker thread for updating from Flickr."""

    def __init__(self, proxy_callback=None, progress_callback=None, done_callback=None):
        threading.Thread.__init__(self)

        self.proxy_callback = proxy_callback
        self.progress_callback = progress_callback
        self.done_callback = done_callback

        self.setDaemon(True)

    def run(self):
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
        for n, fn in enumerate(self.filenames):
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

def idle_proxy(func):
    """Thunk a function into the gobject event loop."""

    def _(proxy):
        func, args, kwargs = proxy
        return func(*args, **kwargs)

    return lambda *args, **kwargs: gobject.idle_add(_, (func, args, kwargs))

def run():
    opts = OPTIONS.parse_args()

    gtk.gdk.threads_init()
    preview = Preview()

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
        done_callback=lambda indexes, filenames: t_image.start(filenames)
    )

    t_flickr.start(opts)
    gtk.main()

    t_flickr.file_index.sync()
    t_flickr.flickr_index.sync()
