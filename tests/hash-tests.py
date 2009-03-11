from __future__ import with_statement

import hashlib
import os.path
import shutil
import tempfile
import unittest

from nose.tools import raises

import pif

from pif.local import HashIndex

class HashIndexNullTests(unittest.TestCase):
    def setUp(self):
        this.index = HashIndex()

    def test_no_hashes(self):
        assert not self.index.keys()

class HashIndexSmallDirTests(unittest.TestCase):
    IMAGE_WIDTH, IMAGE_HEIGHT = 100, 50

    FILES = {
        'abc123.jpeg': 'jpeg',
        'test.jpg': 'jpeg',
        'superjoe.png': 'png',
        'xyzzy.GIF': 'gif',
    }

    def setUp(self):
        # Build some test images!
        self.tempdir = tempfile.mkdtemp()
        images = (os.path.join(self.tempdir, fn)
                  for fn in self.FILES)

        for num, fn in enumerate(images):
            i = PIL.Image.new('RGB', (self.IMAGE_WIDTH, self.IMAGE_HEIGHT))

            # Draw something different so the hash is unique.
            d = PIL.ImageDraw.ImageDraw(i)
            d.text((0, 0), "Test %u" % num)
            del d

            i.save(fn)

        self.index = HashIndex()
        self.index.add_directory(self.tempdir)

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_add(self):
        assert len(self.index) == len(self.FILES)

    def test_rescan(self):
        fn = self.index.keys().pop()
        old_mtime = self.index[fn].last_modified

        os.utime(fn, (old_mtime + 1, old_mtime + 1))
        # TODO: Add a test for refresh returning the modified item(s).
        self.index.refresh()

        assert self.index[fn].last_modified != old_mtime

    def test_add_file_invalid(self):
        b_fn = os.path.join(self.tempdir, 'badfile.png')

        with file(b_fn, 'w') as bf:
            bf.write('abc123')

        self.assertRaises(IOError, self.index.add_file, b_fn)
        assert b_fn not in self.index.files

    def test_adds(self):
        images = (os.path.join(self.tempdir, fn) for fn in self.FILES)

        for fn in images:
            assert fn in self.index

            lf = self.index[fn]
            assert lf.hash == hashlib.sha512(file(fn).read()).digest()

            statinfo = os.stat(fn)
            assert lf.last_modified == statinfo.st_mtime

    # TODO: Save and restore!

    def test_refresh_initial(self):
        for fn, hash in ((fn, lf.hash) for fn, lf in self.file_index.values()):
            assert hash in self.index

            data = file(fn).read()
            th = hashlib.sha512(data[-pif.TAILHASH_SIZE:]).digest()

            assert self.index[h].tailhash == th

            assert lh.format == dict(self.FILES)[fn]
            assert lh.height == self.IMAGE_HEIGHT
            assert lh.width == self.IMAGE_WIDTH

            statinfo = os.stat(fn)
            assert lh.size == statinfo.st_size
