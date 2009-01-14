from __future__ import with_statement

import hashlib
import os.path
import shutil
import tempfile
import unittest

import PIL.Image
import PIL.ImageDraw

from nose.tools import raises

import pif

from pif.local import LocalIndex

class IndexNullTests(unittest.TestCase):
    def test_no_dirs(self):
        i = LocalIndex()

        assert not i.dirs

    def test_invalid_dir_init(self):
        i = LocalIndex(dirs = ['invalid'])
        
        i.refresh()

        assert not i.hashes and not i.files

    def test_invalid_dir_add(self):
        i = LocalIndex()
        i.dirs.append('invalid')

        i.refresh()

        assert not i.hashes and not i.files

class IndexSmallDirTests(unittest.TestCase):
    IMAGE_WIDTH, IMAGE_HEIGHT = 100, 50

    FILES = [('test.jpg', 'jpeg'), ('xyzzy.GIF', 'gif'), ('superjoe.png', 'png')]

    def setUp(self):
        # Stage a directory for test images.
        self.tempdir = tempfile.mkdtemp()
        self.index = LocalIndex([self.tempdir])

        # Build some test images!
        images = (os.path.join(self.tempdir, fn) for fn, fmt in self.FILES)

        for num, fn in enumerate(images):
            i = PIL.Image.new('RGB', (self.IMAGE_WIDTH, self.IMAGE_HEIGHT))

            d = PIL.ImageDraw.ImageDraw(i)
            d.text((0, 0), "Test %u" % num)
            del d

            i.save(fn)

        self.index.refresh()

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_add(self):
        assert len(self.index.hashes) == len(self.FILES)
        assert len(self.index.files) == len(self.FILES)

    def test_rescan(self):
        fn = self.index.files.keys().pop()
        old_mtime = self.index.files[fn].last_modified

        os.utime(fn, (old_mtime + 1, old_mtime + 1))
        self.index.refresh()

        assert self.index.files[fn].last_modified != old_mtime

    def test_file_bad(self):
        b_fn = os.path.join(self.tempdir, 'badfile.png')

        with file(b_fn, 'w') as bf:
            bf.write('abc123')

        self.assertRaises(IOError, self.index.scan_file, b_fn)
        assert b_fn not in self.index.files

    def test_hashes(self):
        fn = self.index.files.keys().pop()

        data = file(fn).read()
        h = hashlib.sha512(data).digest()
        th = hashlib.sha512(data[-pif.TAILHASH_SIZE:]).digest()

        assert h in self.index.hashes
        assert self.index.hashes[h].tailhash == th

    def test_extended_types(self):
        images = ((os.path.join(self.tempdir, fn), fmt) for fn, fmt in self.FILES)

        for fn, fmt in images:
            statinfo = os.stat(fn)

            assert fn in self.index.files

            lf = self.index.files[fn]
            assert lf.hash

            lh = lf.hash
            assert lh.format == fmt
            assert lh.height == self.IMAGE_HEIGHT
            assert lh.width == self.IMAGE_WIDTH
            assert lh.size == statinfo.st_size
