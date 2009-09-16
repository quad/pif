import os.path

import minimock

from minimock import Mock

import pif.flickr
import pif.hash
import pif.index
import pif.local

from pif.index import Index

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

        >>> i = Index(['x.jpg', 'y.png', 'z.gif'])  #doctest: +ELLIPSIS
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

        >>> i.source_filenames
        ['x.jpg', 'y.png', 'z.gif']

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

        >>> i = Index([], config_dir='CONFIG')  #doctest: +ELLIPSIS
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
        >>> minimock.mock('pif.flickr.get_proxy', returns=Mock('FlickrProxy'))
        >>> minimock.mock('pif.hash.HashIndex', returns=Mock('HashIndex'))

        >>> i = Index([], Mock('proxy_callback'), Mock('progress_callback'))    #doctest: +ELLIPSIS
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
        >>> minimock.mock('pif.flickr.get_proxy', returns=Mock('FlickrProxy'))
        >>> minimock.mock('pif.local.FileIndex')
        >>> minimock.mock('pif.flickr.PhotoIndex', returns=Mock('PhotoIndex'))
        >>> minimock.mock('pif.hash.HashIndex', returns=Mock('HashIndex'))

        >>> i = Index([], config_dir='CONFIG')    #doctest: +ELLIPSIS
        Called pif.flickr.get_proxy(wait_callback=None)
        Called os.path.isdir('CONFIG')
        Called os.makedirs('CONFIG')
        ...

        >>> minimock.restore()
        """
