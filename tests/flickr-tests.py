import hashlib
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

        get_proxy(key = 'xyzzy')

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

        get_proxy(secret = 'xyzzy')

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

        def bad_api(auth_response):
            raise flickrapi.FlickrError('Error: 108')

        minimock.mock('flickrapi.FlickrAPI.get_token_part_two', returns_func=bad_api)

        self.hit_cb = False

        def cb():
            if self.hit_cb:
                return True
            else:
                self.hit_cb = True

        self.assertRaises(flickrapi.FlickrError, get_proxy, wait_callback=cb)
        assert self.hit_cb

class EmptyIndexTests(unittest.TestCase):
    def test_auto_refresh(self):
        """FlickrIndex refresh on construction."""

        photo_xml = XML("""
                        <rsp>
                            <photos page="1" pages="1" perpage="100" total="1">
                                <photo farm="4" id="2717638353" isfamily="0" isfriend="0" ispublic="1" lastupdate="1227123744" o_height="1024" o_width="1544" originalformat="jpg" originalsecret="1111111111" owner="25046991@N00" secret="xxxxxxxxxx" server="3071" title="87680027.JPG" />
                            </photos>
                        </rsp>""")
        proxy = Mock('FlickrAPI')
        proxy.photos_recentlyUpdated.mock_returns = photo_xml

        # TODO: Mock the HTTP request for the photo. Right now this results in a
        # ServerNotFoundError from httplib2.

        index = FlickrIndex(proxy)

        assert index.last_update == 1227123744, index.last_update

class IndexTests(unittest.TestCase):
    def setUp(self):
        empty_xml = XML("""
                        <rsp>
                            <photos />
                        </rsp>""")
        self.proxy = Mock('FlickrAPI')
        self.proxy.photos_recentlyUpdated.mock_returns = empty_xml

        self.index = FlickrIndex(self.proxy)

    def tearDown(self):
        minimock.restore()

    def test_empty(self):
        """Empty Flickr index"""

        assert self.index.last_update == 1
        assert not self.index.keys()

    def test_refresh_fail_response(self):
        """Failed refresh from Flickr"""

        photos_xml = XML("""
                         <rsp stat="fail">
                            <err code="1234" msg="Test Message" />
                         </rsp>""")
        self.proxy.photos_recentlyUpdated.mock_returns = photos_xml

        self.index.refresh()
        assert not self.index.keys()

    XML_DATA = {
        2717638353: {
            'farm': 4,
            'height': 1024,
            'id': 2717638353,
            'last_update': 1227123744,
            'original_format': 'jpg',
            'original_secret': '1111111111',
            'server': 3071,
            'size': 12345,
            'width': 1544,
        },

        2658720703: {
            'farm': 3,
            'height': 1500,
            'id': 2658720703,
            'last_update': 1226520673,
            'original_format': 'jpg',
            'original_secret': 'yyyyyyyyyy',
            'server': 2126,
            'size': 53241,
            'width': 1000,
        },

        2740209939: {
            'farm': 4,
            'height': 2736,
            'id': 2740209939,
            'last_update': 1222928301,
            'original_format': 'jpg',
            'original_secret': '3333333333',
            'server': 3108,
            'size': 98764,
            'width': 3648,
        }
    }

    def _mock_photos_http(self):
        class MockResponse(dict):
            def __init__(self, status, length):
                self.status = status
                self['content-range'] = '%u-%u/%u' % ((length - 513), (length - 1), length)

        responses = []

        for id, values in self.XML_DATA.iteritems():
            data = ('*' * pif.TAILHASH_SIZE + str(id))[:512]
            values['tailhash'] = hashlib.sha512(data).digest()

            responses.append((MockResponse(206, values['size']), data))

        import httplib2
        minimock.mock('httplib2.Http.request', returns_iter=responses)
    
    def _check_photo_data(self, photos):
        assert len(photos) == len(self.XML_DATA), "len(photos) == %u, len(self.XML_DATA) == %u" % (len(photos), len(self.XML_DATA))

        for id, values in self.XML_DATA.iteritems():
            for name, result in values.iteritems():
                assert getattr(photos[id], name) == result, "FlickrPhoto(%u).%s != %s (is %s)" % \
                        (id, name, result, getattr(photos[id], name))

    def test_refresh_empty_response(self):
        """Empty response from Flickr"""

        photos_xml = XML("""
                        <rsp>
                            <photos />
                        </rsp>""")
        self.proxy.photos_recentlyUpdated.mock_returns = photos_xml

        self.index.refresh()
        assert not self.index.keys()

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

        self._mock_photos_http()

        self.index.refresh()

        self._check_photo_data(self.index)
        assert self.index.last_update == 1227123744

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

        self._mock_photos_http()

        self.index.refresh()

        self._check_photo_data(self.index)
        assert self.index.last_update == 1227123744

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

        self._mock_photos_http()
        self.index.refresh()
        self._check_photo_data(self.index)

        # Make a noticable change that isn't reflected in the user data.

        self.index[2717638353].original_format = 'gif'
        
        # Refresh again...

        self._mock_photos_http()
        self.index.refresh()

        assert self.index[2717638353].original_format == 'gif'
