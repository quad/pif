import logging
import Queue
import threading

from pif.ui import common_run

LOG = logging.getLogger(__name__)

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

class Loader(threading.Thread):
    """Generic worker thread for offloading IO-heavy loads."""

    def __init__(self, loading_callback=None, work_callback=None, done_callback=None):
        threading.Thread.__init__(self)

        self.loading_callback = loading_callback
        self.work_callback = work_callback
        self.done_callback = done_callback

        self.setDaemon(True)

    def run(self):
        queue = Queue.Queue()

        if self.loading_callback:
            self.loading_callback(queue)

        fns = []
        for fn in self.filenames:
            if self.work_callback:
                self.work_callback(queue, fn)
            fns.append(fn)
        queue.put(None)

        queue.join()

        if self.done_callback:
            self.done_callback(fns)

    def start(self, filenames):
        self.filenames = filenames

        threading.Thread.start(self)

class FlickrUploader(threading.Thread):
    """Worker thread for uploading to Flickr."""

    def __init__(self, proxy, progress_callback=None, done_callback=None):
        threading.Thread.__init__(self)

        self.proxy = proxy
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

                yield self.proxy.upload(filename=fn, callback=_)

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
