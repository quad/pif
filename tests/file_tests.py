from __future__ import with_statement

import os.path
import shutil
import tempfile
import time
import unittest

import PIL.Image
import PIL.ImageDraw

from nose.tools import raises

import pif

from pif.local import FileIndex


class FileIndexNullTests(unittest.TestCase):
    """Uninitialized FileIndex API Tests."""

    def setUp(self):
        self.index_fn = tempfile.mktemp()  # OK to use as we're just testing...
        self.index = FileIndex(self.index_fn)

    def tearDown(self):
        os.remove(self.index_fn)

    def test_no_hashes(self):
        """Empty FileIndex is empty"""
        assert not self.index.keys()


class FileIndexSmallDirTests(unittest.TestCase):
    """FileIndex tests with a small test fixture."""

    IMAGE_WIDTH, IMAGE_HEIGHT = 100, 50

    FILES = {
        'abc123.jpeg': 'jpeg',
        'test.jpg': 'jpeg',
        'superjoe.png': 'png',
        'xyzzy.GIF': 'gif',
    }

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.index = FileIndex(os.path.join(self.tempdir, 'index'))

        # Build some test images!
        self.shorthashes = {}

        for num, meta in enumerate(self.FILES.iteritems()):
            basename, format = meta
            fn = os.path.join(self.tempdir, basename)

            i = PIL.Image.new('RGB', (self.IMAGE_WIDTH, self.IMAGE_HEIGHT))

            # Draw something different so the hash is unique.
            d = PIL.ImageDraw.ImageDraw(i)
            d.text((0, 0), "Test %u" % num)

            i.save(fn)

            # Gather the metadata to create the shorthash.
            statinfo = os.stat(fn)

            with file(fn) as f:
                f.seek(-pif.TAILHASH_SIZE, 2)
                tailhash = f.read()

            self.shorthashes[fn] = pif.make_shorthash(
                tailhash,
                format,
                statinfo.st_size,
                self.IMAGE_WIDTH,
                self.IMAGE_HEIGHT,
            )

            # Load the image into the cache.
            self.index[fn]

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_add(self):
        """Images able to be added to FileIndex"""

        assert len(self.index) == len(self.FILES)

    def test_rescan(self):
        """FileIndex detects changed images."""

        fn = self.index.keys().pop()
        old_shorthash = self.index[fn]

        # Draw on top of the original image to change the hash.
        i = PIL.Image.new('RGB', (999, 999), color=2)

        d = PIL.ImageDraw.ImageDraw(i)
        d.text((0, 0), 'Something new!')

        time.sleep(1)   # The timestamp must tick.
        i.save(fn)

        assert self.index[fn] != old_shorthash

    @raises(KeyError)
    def test_add_file_invalid(self):
        """Invalid images ignored by FileIndex"""

        b_fn = os.path.join(self.tempdir, 'badfile.png')

        with file(b_fn, 'w') as bf:
            bf.write('abc123')

        self.index[b_fn]

    def test_adds(self):
        """FileIndex calculates shorthashes correctly"""

        images = (os.path.join(self.tempdir, fn) for fn in self.FILES)

        for fn in images:
            assert fn in self.index

            shorthash = self.index[fn]
            assert self.index[fn] == self.shorthashes[fn], \
                    "Index %s\nTest %s" % (
                        repr(self.index[fn]),
                        repr(self.shorthashes[fn]),
                    )

    # TODO: Save and restore!
