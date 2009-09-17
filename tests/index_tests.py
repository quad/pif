import os.path

import minimock

from minimock import Mock
from nose.tools import raises

import pif.flickr
import pif.hash
import pif.index
import pif.local

from pif.index import Index

from tests.mock import MockDict


class TestIndexInit:
    """Tests for initializing the Index."""

    def test_basic(self):
        """
        Basic initialization of a UI Shell

        >>> minimock.mock('os.path.isdir', returns=True)
        >>> minimock.mock('pif.flickr.get_proxy', returns=Mock('FlickrProxy'))
        >>> minimock.mock('pif.local.FileIndex')
        >>> minimock.mock('pif.flickr.PhotoIndex', returns=Mock('PhotoIndex'))
        >>> minimock.mock('pif.hash.HashIndex', returns=Mock('HashIndex'))

        >>> i = Index()  #doctest: +ELLIPSIS
        Called pif.flickr.get_proxy(wait_callback=None)
        Called os.path.isdir(...)
        Called pif.local.FileIndex(...)
        Called pif.flickr.PhotoIndex(
            <Mock 0x... FlickrProxy>,
            ...)
        Called pif.hash.HashIndex(
            <Mock 0x... PhotoIndex>,
            ...)
        Called HashIndex.refresh(progress_callback=None)

        >>> minimock.restore()
        """


    def test_alternate_config_dir(self):
        """
        Use an alternate configuration directory.

        >>> minimock.mock('os.path.isdir', returns=True)
        >>> minimock.mock('pif.flickr.get_proxy', returns=Mock('FlickrProxy'))
        >>> minimock.mock('pif.local.FileIndex')
        >>> minimock.mock('pif.flickr.PhotoIndex', returns=Mock('PhotoIndex'))
        >>> minimock.mock('pif.hash.HashIndex', returns=Mock('HashIndex'))

        >>> i = Index(config_dir='CONFIG')  #doctest: +ELLIPSIS
        Called pif.flickr.get_proxy(wait_callback=None)
        Called os.path.isdir('CONFIG')
        Called pif.local.FileIndex('CONFIG/files.db')
        Called pif.flickr.PhotoIndex(<Mock 0x... FlickrProxy>, 'CONFIG/photos.db')
        Called pif.hash.HashIndex(<Mock 0x... PhotoIndex>, 'CONFIG/hashes.db')
        ...

        >>> minimock.restore()
        """


    def test_cbs(self):
        """
        Check Index callbacks.

        >>> minimock.mock('os.path.isdir', returns=True)
        >>> minimock.mock('pif.flickr.get_proxy')
        >>> minimock.mock('pif.hash.HashIndex', returns=Mock('HashIndex'))

        >>> i = Index(Mock('proxy_callback'), Mock('progress_callback'))    #doctest: +ELLIPSIS
        Called pif.flickr.get_proxy(wait_callback=<Mock 0x... proxy_callback>)
        ...
        Called HashIndex.refresh(progress_callback=<Mock 0x... progress_callback>)

        >>> minimock.restore()
        """


    def test_makedirs(self):
        """
        Ensure the configuration directory is created.

        >>> minimock.mock('os.path.isdir', returns=False)
        >>> minimock.mock('os.makedirs')
        >>> minimock.mock('pif.flickr.get_proxy')
        >>> minimock.mock('pif.local.FileIndex')
        >>> minimock.mock('pif.flickr.PhotoIndex')
        >>> minimock.mock('pif.hash.HashIndex', returns=Mock('HashIndex'))

        >>> i = Index(config_dir='CONFIG')    #doctest: +ELLIPSIS
        Called pif.flickr.get_proxy(wait_callback=None)
        Called os.path.isdir('CONFIG')
        Called os.makedirs('CONFIG')
        ...

        >>> minimock.restore()
        """


class TestIndexFiles:
    """Tests for indexing of files."""

    def setUp(self):
        minimock.mock('os.path.isdir', returns=True)
        minimock.mock('pif.flickr.get_proxy')

        self.files = {}
        minimock.mock('pif.local.FileIndex', returns=self.files)

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


class TestIndexCommit:
    """Index doctests."""

    def test_upload(self):
        """
        Upload of a valid file
        
        >>> minimock.mock('os.path.isdir', returns=True)
        >>> proxy = Mock('FlickrProxy')
        >>> minimock.mock('pif.flickr.get_proxy', returns=proxy)

        >>> files = {'x.jpg': 'hash'}
        >>> minimock.mock('pif.local.FileIndex', returns=files)
        >>> minimock.mock('pif.flickr.PhotoIndex', returns=Mock('PhotoIndex'))
        >>> minimock.mock('pif.hash.HashIndex', returns=Mock('HashIndex'))

        >>> i = Index() #doctest: +ELLIPSIS
        Called pif.flickr.get_proxy(wait_callback=None)
        ...

        >>> i.upload('x.jpg')
        Called FlickrProxy.upload('x.jpg', callback=None)

        >>> minimock.restore()
        """


    def test_upload_cb(self):
        """
        Upload of a valid file
        
        >>> minimock.mock('os.path.isdir', returns=True)
        >>> proxy = Mock('FlickrProxy')
        >>> minimock.mock('pif.flickr.get_proxy', returns=proxy)

        >>> files = {'x.jpg': 'hash'}
        >>> minimock.mock('pif.local.FileIndex', returns=files)
        >>> minimock.mock('pif.flickr.PhotoIndex', returns=Mock('PhotoIndex'))
        >>> minimock.mock('pif.hash.HashIndex', returns=Mock('HashIndex'))

        >>> i = Index() #doctest: +ELLIPSIS
        Called pif.flickr.get_proxy(wait_callback=None)
        ...

        >>> i.upload('x.jpg', Mock('upload_callback'))  #doctest: +ELLIPSIS
        Called FlickrProxy.upload('x.jpg', callback=<Mock 0x... upload_callback>)

        >>> minimock.restore()
        """

    def test_close(self):
        """
        Closing the index commits
        
        >>> minimock.mock('os.path.isdir', returns=True)
        >>> minimock.mock('pif.flickr.get_proxy')

        >>> minimock.mock('pif.local.FileIndex', returns=Mock('FileIndex'))
        >>> minimock.mock('pif.flickr.PhotoIndex', returns=Mock('PhotoIndex'))
        >>> minimock.mock('pif.hash.HashIndex', returns=Mock('HashIndex'))

        >>> i = Index() #doctest: +ELLIPSIS
        Called pif.flickr.get_proxy(wait_callback=None)
        ...

        >>> i.close()
        Called FileIndex.close()
        Called PhotoIndex.close()
        Called HashIndex.close()

        >>> minimock.restore()
        """
