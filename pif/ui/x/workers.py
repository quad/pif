import logging
import sys
import threading

from pif.flickr import FlickrError
from pif.ui import common_run

LOG = logging.getLogger(__name__)


class WorkerThread(threading.Thread):
    """
    Generic worker thread implementation.

    Requires a mixin implementing CallbackWrapper.
    """

    class CallbackWrapper:
        """A stub callback wrapper."""

        def __init__(self):
            raise NotImplementedError

        def __setattr__(self, name, value):
            raise NotImplementedError

    def __init__(self):
        threading.Thread.__init__(self)

        self.args = ((), ())
        self.cbs = self.CallbackWrapper()

        def _(exc_info):
            t, v, tb = exc_info
            raise t, v, tb
        self.cbs._exception = _

        self.setDaemon(True)

    def run(self):
        args, kwargs = self.args

        try:
            self.do(*args, **kwargs)
        except SystemExit:
            raise
        except:
            self.cbs._exception(sys.exc_info())

    def do(self, *args, **kwargs):
        raise NotImplementedError

    def start(self, *args, **kwargs):
        self.args = (args, kwargs)

        threading.Thread.start(self)


class FlickrUpdater(WorkerThread):
    """Worker thread for updating from Flickr."""

    def __init__(self, proxy_callback=None, progress_callback=None, done_callback=None):
        WorkerThread.__init__(self)

        self.cbs.proxy = proxy_callback
        self.cbs.progress = progress_callback
        self.cbs.done = done_callback

        self.setDaemon(True)

    def do(self, opts):
        if self.cbs.proxy:
            self.cbs.proxy()

        indexes, filenames = common_run(opts, self.cbs.proxy, self.cbs.progress)

        if self.cbs.done:
            self.cbs.done(indexes, filenames)


class Loader(WorkerThread):
    """Generic worker thread for offloading IO-heavy loads."""

    def __init__(self, loading_callback=None, work_callback=None, done_callback=None):
        WorkerThread.__init__(self)

        self.cbs.loading = loading_callback
        self.cbs.work = work_callback
        self.cbs.done = done_callback

        self.setDaemon(True)

    def do(self, items):
        if self.cbs.loading:
            self.cbs.loading()

        results = []
        for i in items:
            if self.cbs.work:
                self.cbs.work(i)
            results.append(i)

        if self.cbs.done:
            self.cbs.done(results)


class FlickrUploader(WorkerThread):
    """Worker thread for uploading to Flickr."""

    def __init__(self, proxy, progress_callback=None, done_callback=None):
        WorkerThread.__init__(self)

        self.proxy = proxy

        self.cbs.progress = progress_callback
        self.cbs.done = done_callback

        self.setDaemon(True)

    def do(self, filenames):
        ids = []

        def _upload(fns):
            for n, fn in enumerate(fns):
                if self.cbs.progress:
                    def _(progress, done):
                        if done:
                            p = n + 1
                        else:
                            p = n + (progress / 100)
                        self.cbs.progress(p, len(filenames))
                else:
                    _ = None

                yield self.proxy.upload(filename=fn, callback=_)

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

        if self.cbs.done:
            self.cbs.done(len(filenames) == len(ids), url)
