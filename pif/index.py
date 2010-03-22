import os
import os.path

import pif.flickr
import pif.hash
import pif.local

try:
    import xdg.BaseDirectory

    CONFIG_DIR = os.path.join(xdg.BaseDirectory.xdg_data_home, 'pif')
except ImportError:
    CONFIG_DIR = os.path.expanduser('~/.pif')


class Index:
    def __init__(self,
                 proxy_callback=None,
                 progress_callback=None,
                 config_dir=CONFIG_DIR):
        self.cb_progress = progress_callback
        self.cb_proxy = proxy_callback
        self.config_dir = config_dir

        self._init_proxy()
        self._init_indexes()

    def _init_proxy(self):
        if 'PIF_NO_REFRESH' in os.environ:
            self.proxy = None
        else:
            self.proxy = pif.flickr.get_proxy(wait_callback=self.cb_proxy)

    def _init_indexes(self):
        files_fn = os.path.join(self.config_dir, 'files.db')
        photos_fn = os.path.join(self.config_dir, 'photos.db')
        hashes_fn = os.path.join(self.config_dir, 'hashes.db')

        if not os.path.isdir(self.config_dir):
            os.makedirs(self.config_dir)

        self.files = pif.local.FileIndex(files_fn)

        self.photos = pif.flickr.PhotoIndex(self.proxy, photos_fn)
        self.hashes = pif.hash.HashIndex(self.photos, hashes_fn)

        if 'PIF_NO_REFRESH' not in os.environ:
            self.hashes.refresh(progress_callback=self.cb_progress)

    def type(self, filename):
        try:
            if self.hashes.get(self.files[filename], []):
                return 'old'
        except KeyError:
            return 'invalid'

        return 'new'

    def ignore(self, filename):
        h = self.files[filename]

        if None not in self.hashes.get(h, []):
            self.hashes.setdefault(h, []).append(None)

    def upload(self, filename, callback=None):
        self.files[filename]    # Ensure the file is valid.
        return self.proxy.upload(filename, callback=callback)

    def sync(self):
        self.hashes.sync()
        self.photos.sync()
        self.files.sync()
