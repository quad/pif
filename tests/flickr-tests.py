import unittest

import flickrapi

from nose.exc import SkipTest
from nose.tools import raises

from pif.flickr import get_proxy

class ProxyTests(unittest.TestCase):
    """Flickr proxy tests."""

    @raises(flickrapi.FlickrError)
    def test_invalid_key(self):
        get_proxy(key = 'xyzzy')

    @raises(flickrapi.FlickrError)
    def test_invalid_secret(self):
        get_proxy(secret = 'xyzzy')

    @raises(flickrapi.FlickrError)
    def test_invalid_key_and_secret(self):
        get_proxy('abc', '123')

    @raises(flickrapi.FlickrError)
    def test_reject(self):
        raise SkipTest, "Flickr doesn't reject API requests?"

    def test_ok(self):
        self.hit_cb = False

        def cb():
            self.hit_cb = True

        assert isinstance(get_proxy(wait_callback = cb), flickrapi.FlickrAPI)
        assert self.hit_cb

    @raises(IOError)
    def test_offline(self):
        raise SkipTest, "How can we simulate being offline?"

class FlickrIndexTests(unittest.TestCase):
    """Flickr index tests."""
