from __future__ import with_statement

import hashlib
import itertools
import os
import re

import PIL.Image

import pif

class LocalFile:
    def __init__(self, filename, last_modified):
        self.filename = filename
        self.last_modified = last_modified

class LocalHash:
    def __init__(self, hash):
        self.hash = hash

class LocalIndex:
    EXTENSIONS = ('gif',
                  'jpeg', 'jpg',
                  'png',)

    RE_IMAGES = re.compile(r".*\.(%s)$" % '|'.join(EXTENSIONS),
                           re.IGNORECASE)

    def __init__(self, dirs=None):
        self.dirs = dirs if dirs else []
        self.files = {}
        self.hashes = {}

    def scan_file(self, filename):
        statinfo = os.stat(filename)
        lf = self.files.get(filename, LocalFile(filename, 0))

        # Abort if the file hasn't been modified.
        if lf.last_modified == statinfo.st_mtime:
            return

        # Validate the potential image.
        image = PIL.Image.open(filename)
        image.verify()

        # Rescan the file to update the hash entry.
        with file(filename) as f:
            data = f.read()

            hash_full = hashlib.sha512(data).digest()
            hash_tail = hashlib.sha512(data[-pif.TAILHASH_SIZE:]).digest()

            del data

        lh = self.hashes.get(hash, LocalHash(hash_full))

        lh.format = image.format.lower()
        lh.size = statinfo.st_size
        lh.tailhash = hash_tail
        lh.width, lh.height = image.size

        lf.hash = lh
        lf.last_modified = statinfo.st_mtime

        self.files[filename] = lf
        self.hashes[hash_full] = lh

    def refresh(self):
        # Search directory structure for all image files.

        def images_in_dir(directory):
            for root, dirs, files in os.walk(directory):
                for fn in filter(self.RE_IMAGES.match, files):
                    yield os.path.abspath(os.path.join(root, fn))

        image_files = itertools.chain(*(images_in_dir(d) for d in self.dirs))

        # Invalid files that exist, and new files should be updated.

        for fn in image_files:
            self.scan_file(fn)
