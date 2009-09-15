import logging
import os
import shelve

import PIL.Image

from pif import TAILHASH_SIZE, make_shorthash

LOG = logging.getLogger(__name__)


class FileIndex(object, shelve.DbfilenameShelf):
    """Cache for local file shorthashes."""

    def __init__(self, filename):
        shelve.DbfilenameShelf.__init__(self, filename)

    def __getitem__(self, filename):
        if filename in self:
            last_modified, shorthash = shelve.DbfilenameShelf.__getitem__(self, filename)
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
            f.seek(-TAILHASH_SIZE, 2)
            tailhash = f.read()

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
