import os

import PIL.Image

import pif.dictdb

from pif import TAILHASH_SIZE, make_shorthash


class FileIndex(pif.dictdb.DictDB):
    """Cache for local file shorthashes."""

    def __init__(self, filename):
        pif.dictdb.DictDB.__init__(self, filename)

    def __getitem__(self, filename):
        if filename in self:
            last_modified, shorthash = pif.dictdb.DictDB.__getitem__(
                self, filename)
        else:
            last_modified, shorthash = None, None

        # Abort if the file hasn't been modified.
        statinfo = os.stat(filename)

        if last_modified == statinfo.st_mtime:
            return shorthash

        # Validate the potential image.
        try:
            image = PIL.Image.open(filename)
            image.verify()
        except IOError:
            raise KeyError(filename)

        # Gather the metadata to create the shorthash.
        with file(filename) as f:
            try:
                f.seek(-TAILHASH_SIZE, 2)
            except IOError:
                # Maybe the file doesn't have TAILHASH_SIZE bytes to spare...
                f.seek(0)

            tailhash = f.read(TAILHASH_SIZE)

        shorthash = make_shorthash(
            tailhash,
            image.format,
            statinfo.st_size,
            image.size[0],
            image.size[1],
        )

        # Cache the shorthash.
        self[filename] = (statinfo.st_mtime, shorthash)

        return shorthash
