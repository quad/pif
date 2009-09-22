import os.path

import minimock

from minimock import Mock
from nose.tools import raises

import pif.flickr
import pif.hash
import pif.local

from pif.index import Index

from tests.mock import MockDict


class TestIndexFiles:
    """Tests for indexing of files."""

    def setUp(self):
        minimock.mock('os.path.isdir', returns=True)
        minimock.mock('pif.flickr.get_proxy')

        self.files = {}
        minimock.mock('pif.local.FileIndex', returns=self.files)

        minimock.mock('pif.flickr.PhotoIndex', returns=Mock('PhotoIndex'))

        self.hashes = MockDict('HashIndex')
        minimock.mock('pif.hash.HashIndex', returns=self.hashes)
        self.hashes.get.mock_returns_func = self.hashes.mock_items.get

        self.index = Index()


    def tearDown(self):
        minimock.restore()


    def test_basic(self):
        """Index supplies new files"""

        self.files['x.jpg'] = 'hash'

        assert self.index.type('x.jpg') == 'new'


    def test_skipped(self):
        """Index skips already uploaded files"""

        self.files['x.jpg'] = 'hash'
        self.hashes['hash'] = ['123']

        assert self.index.type('x.jpg') == 'old'


    def test_invalid(self):
        """Index skips invalid files"""

        assert self.index.type('x.jpg') == 'invalid'


class TestIndexChanges:
    """Tests for modifying the Index."""

    def setUp(self):
        minimock.mock('os.path.isdir', returns=True)
        minimock.mock('pif.flickr.get_proxy')

        self.files = {}
        minimock.mock('pif.local.FileIndex', returns=self.files)

        minimock.mock('pif.flickr.PhotoIndex', returns=Mock('PhotoIndex'))

        self.hashes = MockDict('HashIndex')
        minimock.mock('pif.hash.HashIndex', returns=self.hashes)
        self.hashes.get.mock_returns_func = self.hashes.mock_items.get

        self.index = Index()


    def tearDown(self):
        minimock.restore()


    def test_ignore(self):
        """Index ignores a valid file"""

        self.files['x.jpg'] = 'hash'
        self.hashes['hash'] = []

        assert self.index.type('x.jpg') == 'new'

        self.index.ignore('x.jpg')

        assert self.index.type('x.jpg') == 'old'


    @raises(KeyError)
    def test_ignore_invalid(self):
        """Index barfs when ignoring an invalid file"""

        assert self.index.type('x.jpg') == 'invalid'
        self.index.ignore('x.jpg')


    def test_ignore_repeat(self):
        """Index ignoring is idempotent"""

        self.files['x.jpg'] = 'hash'
        self.hashes['hash'] = []

        self.index.ignore('x.jpg')
        self.index.ignore('x.jpg')

        assert self.index.type('x.jpg') == 'old'
        assert self.hashes['hash'] == [None]


    @raises(KeyError)
    def test_upload_no_file(self):
        """Try to upload without a valid file"""

        self.index.upload('x.jpg')
