import hashlib
import os
import tempfile
import unittest

from xml.etree.ElementTree import XML

import flickrapi
import minimock

from minimock import Mock
from nose.exc import SkipTest
from nose.tools import raises

import pif

from pif.flickr import get_proxy, FlickrIndex

class OnlineProxyTests(unittest.TestCase):
    """Flickr proxy tests."""

    def tearDown(self):
        minimock.restore()

    @raises(flickrapi.FlickrError)
    def test_invalid_key(self):
        """Proxy with invalid key"""

        frob = Mock('frob')
        frob.read.mock_returns = """<?xml version="1.0" encoding="utf-8" ?>
<rsp stat="fail">
    <err code="100" msg="Invalid API Key (Key not found)" />
</rsp>"""

        import urllib
        minimock.mock('urllib.urlopen', returns=frob)

        get_proxy(key='xyzzy')

    @raises(flickrapi.FlickrError)
    def test_invalid_secret(self):
        """Proxy with invalid secret"""

        frob = Mock('frob')
        frob.read.mock_returns = """<?xml version="1.0" encoding="utf-8" ?>
<rsp stat="fail">
    <err code="96" msg="Invalid signature" />
</rsp>"""

        import urllib
        minimock.mock('urllib.urlopen', returns=frob)

        get_proxy(secret='xyzzy')

    @raises(IOError)
    def test_offline(self):
        """Proxy when offline"""

        import urllib
        minimock.mock('urllib.urlopen', raises=IOError)

        get_proxy()

    @raises(flickrapi.FlickrError)
    def test_reject(self):
        """Rejected proxy"""

        minimock.mock('flickrapi.FlickrAPI.get_token_part_one')
        minimock.mock('flickrapi.FlickrAPI.get_token_part_two', raises=flickrapi.FlickrError)

        get_proxy()

    def test_ok(self):
        """OK proxy"""

        minimock.mock('flickrapi.FlickrAPI.get_token_part_one')
        minimock.mock('flickrapi.FlickrAPI.get_token_part_two', returns=True)

        assert isinstance(get_proxy(), flickrapi.FlickrAPI)

    def test_cb(self):
        """Callback from proxy"""

        minimock.mock('flickrapi.FlickrAPI.get_token_part_one')

        def _bad_api(auth_response):
            raise flickrapi.FlickrError('Error: 108')

        minimock.mock('flickrapi.FlickrAPI.get_token_part_two', returns_func=_bad_api)

        self.hit_cb = False

        def _cb():
            if self.hit_cb:
                return True
            else:
                self.hit_cb = True

        self.assertRaises(flickrapi.FlickrError, get_proxy, wait_callback=_cb)
        assert self.hit_cb

class IndexTests(unittest.TestCase):
    """Flickr Index API tests."""

    def setUp(self):
        self.proxy = Mock('FlickrAPI')
        self.index_fn = tempfile.mktemp()  # OK to use as we're just testing...
        self.index = FlickrIndex(self.proxy, filename=self.index_fn)

    def tearDown(self):
        minimock.restore()
        os.remove(self.index_fn)

    def test_empty(self):
        """Empty Flickr index"""

        assert not self.index.keys()
        assert self.index.last_update == 1

    def test_refresh_fail_response(self):
        """Failed refresh from Flickr"""

        photos_xml = XML("""
                         <rsp stat="fail">
                            <err code="1234" msg="Test Message" />
                         </rsp>""")
        self.proxy.photos_recentlyUpdated.mock_returns = photos_xml

        self.index.refresh()
        assert not self.index.keys()
        assert self.index.last_update == 1

    def test_refresh_empty_response(self):
        """Empty response from Flickr"""

        photos_xml = XML("""
                        <rsp>
                            <photos />
                        </rsp>""")
        self.proxy.photos_recentlyUpdated.mock_returns = photos_xml

        self.index.refresh()
        assert not self.index.keys()
        assert self.index.last_update == 1

    # TODO: Test progress callbacks.
    # TODO: Test .add()
    # TODO: Test shorthash collisions.
    # TODO: Test .ignore()

class IndexRefreshTests(unittest.TestCase):
    """Flickr Index refresh tests."""

    XML_DATA = {
        '2717638353': {
            'farm': 4,
            'height': 1024,
            'id': 2717638353,
            'lastupdate': 1227123744,
            'original_format': 'jpg',
            'original_secret': '1111111111',
            'server': 3071,
            'size': 12345,
            'width': 1544,
        },

        '2658720703': {
            'farm': 3,
            'height': 1500,
            'id': 2658720703,
            'lastupdate': 1226520673,
            'original_format': 'jpg',
            'original_secret': 'yyyyyyyyyy',
            'server': 2126,
            'size': 53241,
            'width': 1000,
        },

        '2740209939': {
            'farm': 4,
            'height': 2736,
            'id': 2740209939,
            'lastupdate': 1222928301,
            'original_format': 'jpg',
            'original_secret': '3333333333',
            'server': 3108,
            'size': 98764,
            'width': 3648,
        }
    }

    def setUp(self):
        self.proxy = Mock('FlickrAPI')
        self.index_fn = tempfile.mktemp()  # OK to use as we're just testing...
        self.index = FlickrIndex(self.proxy, filename=self.index_fn)

        self.shorthashes = {}
        self._mock_photos_http()

    def tearDown(self):
        minimock.restore()
        os.remove(self.index_fn)

    def _mock_photos_http(self):
        def _mock_sh(photo):
            id = photo['id']

            data = ('*' * pif.TAILHASH_SIZE + str(id))[:512]
            values = self.XML_DATA[id]
            shorthash = pif.make_shorthash(
                data,
                values['original_format'],
                values['size'],
                values['width'],
                values['height'],
            )

            self.shorthashes[id] = shorthash
            return shorthash

        minimock.mock('pif.flickr.get_photo_shorthash', returns_func=_mock_sh)
    
    def _check_photo_data(self, photos):
        assert len(photos) == len(self.XML_DATA), "len(photos) == %u, len(self.XML_DATA) == %u" % (len(photos), len(self.XML_DATA))

        # Check data against the dictionary.
        for id, values in self.XML_DATA.iteritems():
            shorthash = self.shorthashes[id]
            assert id, values['lastupdate'] == photos[shorthash]

        assert photos.last_update == max([v['lastupdate'] for v in self.XML_DATA.values()])

    def test_refresh_single_page(self):
        """Single page, multiple photos"""

        photos_xml = XML("""
                        <rsp>
                            <photos page="1" pages="1" perpage="100" total="3">
                                <photo farm="4" id="2717638353" isfamily="0" isfriend="0" ispublic="1" lastupdate="1227123744" o_height="1024" o_width="1544" originalformat="jpg" originalsecret="1111111111" owner="25046991@N00" secret="xxxxxxxxxx" server="3071" title="87680027.JPG" />
                                <photo farm="4" id="2740209939" isfamily="0" isfriend="0" ispublic="1" lastupdate="1222928301" o_height="2736" o_width="3648" originalformat="jpg" originalsecret="3333333333" owner="25046991@N00" secret="zzzzzzzzzz" server="3108" title="IMG_0394.JPG" />
                                <photo farm="3" id="2658720703" isfamily="0" isfriend="0" ispublic="1" lastupdate="1226520673" o_height="1500" o_width="1000" originalformat="jpg" originalsecret="yyyyyyyyyy" owner="25046991@N00" secret="2222222222" server="2126" title="16.jpg" />
                            </photos>
                        </rsp>""")
        self.proxy.photos_recentlyUpdated.mock_returns = photos_xml

        self.index.refresh()
        self._check_photo_data(self.index)

    def test_refresh_multi_page(self):
        """Multiple pages, single photos"""

        photos_xml_1 = XML("""
                        <rsp>
                            <photos page="1" pages="3" perpage="1" total="3">
                                <photo farm="4" id="2717638353" isfamily="0" isfriend="0" ispublic="1" lastupdate="1227123744" o_height="1024" o_width="1544" originalformat="jpg" originalsecret="1111111111" owner="25046991@N00" secret="xxxxxxxxxx" server="3071" title="87680027.JPG" />
                            </photos>
                        </rsp>""")

        photos_xml_2 = XML("""
                        <rsp>
                            <photos page="2" pages="3" perpage="1" total="3">
                                <photo farm="4" id="2740209939" isfamily="0" isfriend="0" ispublic="1" lastupdate="1222928301" o_height="2736" o_width="3648" originalformat="jpg" originalsecret="3333333333" owner="25046991@N00" secret="zzzzzzzzzz" server="3108" title="IMG_0394.JPG" />
                            </photos>
                        </rsp>""")

        photos_xml_3 = XML("""
                        <rsp>
                            <photos page="3" pages="3" perpage="1" total="3">
                                <photo farm="3" id="2658720703" isfamily="0" isfriend="0" ispublic="1" lastupdate="1226520673" o_height="1500" o_width="1000" originalformat="jpg" originalsecret="yyyyyyyyyy" owner="25046991@N00" secret="yyyyyyyyyy" server="2126" title="16.jpg" />
                            </photos>
                        </rsp>""")
        self.proxy.photos_recentlyUpdated.mock_returns = None
        self.proxy.photos_recentlyUpdated.mock_returns_iter = iter([photos_xml_1, photos_xml_2, photos_xml_3])

        self.index.refresh()
        self._check_photo_data(self.index)

    def test_refresh_duplicate(self):
        """Non-destructive updates from Flickr"""

        photos_xml = XML("""
                        <rsp>
                            <photos page="1" pages="1" perpage="100" total="3">
                                <photo farm="4" id="2717638353" isfamily="0" isfriend="0" ispublic="1" lastupdate="1227123744" o_height="1024" o_width="1544" originalformat="jpg" originalsecret="1111111111" owner="25046991@N00" secret="xxxxxxxxxx" server="3071" title="87680027.JPG" />
                                <photo farm="4" id="2740209939" isfamily="0" isfriend="0" ispublic="1" lastupdate="1222928301" o_height="2736" o_width="3648" originalformat="jpg" originalsecret="3333333333" owner="25046991@N00" secret="zzzzzzzzzz" server="3108" title="IMG_0394.JPG" />
                                <photo farm="3" id="2658720703" isfamily="0" isfriend="0" ispublic="1" lastupdate="1226520673" o_height="1500" o_width="1000" originalformat="jpg" originalsecret="yyyyyyyyyy" owner="25046991@N00" secret="2222222222" server="2126" title="16.jpg" />
                            </photos>
                        </rsp>""")
        self.proxy.photos_recentlyUpdated.mock_returns = photos_xml

        # Test the initial refresh.

        self.index.refresh()
        self._check_photo_data(self.index)

        # Make a noticable change that isn't reflected in the user data.

        self.index.ignore('abc123')
        self.index.refresh()

        assert self.index['abc123'] == self.index.STUB

# TODO: Test refresh failures.
# TODO: Test .get_photo_shorthash
# TODO: Test .get_photo_shorthashes
