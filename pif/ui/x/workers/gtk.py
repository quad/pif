import functools

import pygtk
pygtk.require('2.0')
import gobject

import pif.ui.x.workers.generic


class GObjectWorker:
    """A mixin for workers under GObject mainloops."""

    class CallbackWrapper:
        """Callback wrapper using the GObject mainloop."""

        def __init__(self):
            def _(exc_info):
                type, value, traceback = exc_info
                raise type, value, traceback

            self._error = _

        def __setattr__(self, name, value):
            if callable(value):
                value = self._make_callback(value)
            self.__dict__[name] = value

        def _make_callback(self, function):
            assert callable(function)

            def _(*args, **kwargs):
                gobject.idle_add(functools.partial(function, *args, **kwargs))

            return functools.partial(_)


class Loader(GObjectWorker, pif.ui.x.workers.generic.Loader):
    pass


class FlickrUpdater(GObjectWorker, pif.ui.x.workers.generic.FlickrUpdater):
    pass


class FlickrUploader(GObjectWorker, pif.ui.x.workers.generic.FlickrUploader):
    pass
