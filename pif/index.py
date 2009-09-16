import os
import os.path

import pif.flickr
import pif.hash
import pif.local


class Index:
    def __init__(self, filenames, proxy_callback=None, progress_callback=None, config_dir=None):
        self.cb_progress = progress_callback
        self.cb_proxy = proxy_callback
        self.config_dir = config_dir if config_dir else os.path.expanduser('~/.pif')
        self.source_filenames = filenames

        self._init_proxy()
        self._init_indexes()


    def _init_proxy(self):
        self.proxy = pif.flickr.get_proxy(wait_callback=self.cb_proxy)


    def _init_indexes(self):
        files_fn = os.path.join(self.config_dir, 'files.db')
        photos_fn = os.path.join(self.config_dir, 'photos.db')
        hashes_fn = os.path.join(self.config_dir, 'hashes.db')

        if not os.path.isdir(self.config_dir):
            os.makedirs(self.config_dir)

        self.files = pif.local.FileIndex(files_fn)

        p = pif.flickr.PhotoIndex(self.proxy, photos_fn)
        self.hashes = pif.hash.HashIndex(p, hashes_fn)

        self.hashes.refresh(progress_callback=self.cb_progress)


    def ignore(self):
        raise NotImplementedError()


    def upload(self):
        raise NotImplementedError()


    @property
    def filenames(self):
        for fn in self.source_filenames:
            try:
                if self.files[fn] in self.hashes \
                   and len(self.hashes[self.files[fn]]):
                    self.cb_progress('index-skip', (fn, ))
                else:
                    yield fn
            except KeyError:    # Skip invalid files.
                self.cb_progress('index-invalid', (fn, ))
