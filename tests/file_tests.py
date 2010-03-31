from __future__ import with_statement

import json
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

from tests import DATA


class FileIndexNullTests(unittest.TestCase):
    """Uninitialized FileIndex API Tests."""

    def setUp(self):
        self.index_fn = tempfile.mktemp()  # OK to use as we're just testing...
        self.index = FileIndex(self.index_fn)

    def test_no_hashes(self):
        """Empty FileIndex is empty"""
        assert not self.index.keys()


class FileIndexSmallDirTests(unittest.TestCase):
    """FileIndex tests with a small test fixture."""

    IMAGE_WIDTH, IMAGE_HEIGHT = 100, 50

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.index = FileIndex(os.path.join(self.tempdir, 'index'))

        imagedir = os.path.join(DATA, 'images')
        precalc_shs = json.load(file(os.path.join(imagedir, 'shorthashes.json')))

        self.shorthashes = {}

        for fn, sh in precalc_shs.iteritems():
            src = os.path.join(imagedir, fn)
            dest = os.path.join(self.tempdir, fn)

            shutil.copy(src, dest)

            self.shorthashes[dest] = sh
            self.index[dest]

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_add(self):
        """Images able to be added to FileIndex"""

        assert len(self.index) == len(self.shorthashes), "%s != %s" % (self.index, self.shorthashes)

    def test_rescan(self):
        """FileIndex detects changed images"""

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

        for fn in self.shorthashes:
            assert fn in self.index
            assert self.index[fn] == self.shorthashes[fn], \
                    "Index %s\nTest %s" % (
                        repr(self.index[fn]),
                        repr(self.shorthashes[fn]),
                    )

    # TODO: Save and restore!
