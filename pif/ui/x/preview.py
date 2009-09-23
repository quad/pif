import pkg_resources

import pygtk
pygtk.require('2.0')
import gtk
import gtk.glade

import pif.ui.shell

from pif.ui.x.workers.gtk import FlickrUpdater


class StatusUI(object):
    """Mixin for updating the status UI controls."""

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


class LoginCallbacks(StatusUI):
    """Mixin for handling Flickr login worker callbacks."""

    def __init__(self):
        self.index = None

    def proxy_cb(self, *args):
        """Inform about waiting for Flickr."""

        self.set_status('Waiting for authorization from Flickr...')

    def progress_cb(self, state, meta):
        """Update the progress bar from the Flickr update."""

        msgs = {
            'photos': 'Loading update %u of %u from Flickr...' % meta,
            'hashes': 'Indexing photo %u of %u on Flickr...' % tuple(map(int, meta)),
        }

        fraction = float(meta[0]) / float(meta[1])
        self.set_status(msgs[state], fraction)

    def index_cb(self, index):
        """Register the index."""

        self.index = index

        if not self.index:
            self.alert('Couldn\'t connect to Flickr.')


class PreviewWindow(pif.ui.shell.Shell, LoginCallbacks):
    """A preview window."""

    XML = pkg_resources.resource_string(__name__, 'preview.glade')

    def __init__(self):
        pif.ui.shell.Shell.__init__(self)

        LoginCallbacks.__init__(self)

        self._init_gtk()


    def _init_gtk(self):
        # Hookup the widgets through Glade.
        self.glade = gtk.glade.xml_new_from_buffer(self.XML, len(self.XML))
        self.glade.signal_autoconnect(self)

        self.window = self.glade.get_widget('window')

        # Ensure we're graphical.
        if not gtk.gdk.get_display():
            self.option_parser.error('Cannot open display.')

        gtk.gdk.threads_init()


    def run(self):
        # Show the UI!
        self.window.show_all()

        """
        w_thumb = Loader(
            work_callback=preview.load_thumb_cb,
            done_callback=preview.load_thumb_done_cb)
        w_image = Loader(
            loading_callback=preview.load_image_start_cb,
            work_callback=preview.load_image_cb,
            done_callback=lambda filenames: preview.load_image_done_cb(filenames, w_thumb))

        # Let the user select files if none were specified.

        if args:
            w_flickr.start(opts)
        else:
            gobject.idle_add(preview.request_images_cb, lambda fns: w_flickr.start((options, fns)))
        """

        w_flickr = FlickrUpdater(
            proxy_callback=self.proxy_cb,
            progress_callback=self.progress_cb,
            done_callback=self.index_cb)
        w_flickr.start(self)

        gtk.main()


    def on_close(self, widget, user_data=None):
        """Quit, but warn if there are unsaved changes."""

        # TODO: Alert if there are unsaved changes.

        """
        views = map(self.glade.get_widget, ('view_ignore', 'view_upload'))
        changed = map(lambda v: v.props.sensitive and self._view_is_active(v), views)

        if True in changed:
            md = gtk.MessageDialog(
                parent=self.window,
                flags=gtk.DIALOG_MODAL,
                type=gtk.MESSAGE_WARNING,
                buttons=gtk.BUTTONS_OK_CANCEL,
                message_format='There are unsaved changes.\n\nAre you sure you want to exit?')

            resp = md.run()

            # We only cancel if specifically requested.
            if resp != gtk.RESPONSE_OK:
                md.destroy()
                return True
        """

        if self.index:
            self.index.sync()

        gtk.main_quit()
