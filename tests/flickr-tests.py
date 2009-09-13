import doctest
import glob
import os
import os.path
import tempfile
import urllib2

from xml.etree.ElementTree import XML
from xml.parsers.expat import ExpatError

import flickrapi
import minimock

from minimock import Mock
from nose.tools import assert_raises, raises

import pif

from pif.flickr import FlickrError, FlickrIndex, PhotoIndex, get_proxy

from tests import DATA

class TestProxy:
    """Flickr proxy tests."""

    def tearDown(self):
        minimock.restore()

    @raises(FlickrError)
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

    @raises(FlickrError)
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

    @raises(FlickrError)
    def test_bad_xml(self):
        """Bad XML from proxy"""

        minimock.mock('flickrapi.FlickrAPI.get_token_part_one', raises=ExpatError)

        get_proxy()

    @raises(FlickrError)
    def test_reject(self):
        """Rejected proxy"""

        minimock.mock('flickrapi.FlickrAPI.get_token_part_one')
        minimock.mock('flickrapi.FlickrAPI.get_token_part_two', raises=FlickrError)

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
            raise FlickrError('Error: 108: Invalid frob')

        minimock.mock('flickrapi.FlickrAPI.get_token_part_two', returns_func=_bad_api)

        self.hit_cb = False

        def _cb():
            if self.hit_cb:
                return True
            else:
                self.hit_cb = True

        assert_raises(FlickrError, get_proxy, wait_callback=_cb)
        assert self.hit_cb


class TestPhotoIndex:
    """Flickr Photo Index API tests."""

    def setUp(self):
        self.proxy = Mock('FlickrAPI')
        self.index_fn = tempfile.mktemp()  # OK to use as we're just testing...
        self.index = PhotoIndex(self.proxy, filename=self.index_fn)

    def tearDown(self):
        minimock.restore()
        os.remove(self.index_fn)

    def test_init_no_proxy(self):
        """Initialize PhotoIndex with no proxy"""

        i = PhotoIndex(None, self.index_fn)

        assert i is not None

    def test_empty(self):
        """Empty PhotoIndex"""

        assert not self.index.keys()
        assert self.index.last_update == 0

    @raises(AssertionError)
    def test_refresh_fail_no_proxy(self):
        """PhotoIndex refresh fails without a proxy"""

        self.index.proxy = None
        self.index.refresh()

    def test_refresh_no_cb(self):
        """PhotoIndex refresh with no callback"""

        photos_xml = XML("""
                        <rsp>
                            <photos page="1" pages="1">
                                <photo id="2717638353" />
                            </photos>
                        </rsp>""")
        self.proxy.photos_recentlyUpdated.mock_returns = photos_xml

        assert '2717638353' in self.index.refresh()

    def test_refresh_cb(self):
        """Callback from PhotoIndex refresh"""

        photos_xml = XML("""
                        <rsp>
                            <photos page="1" pages="1">
                                <photo id="2717638353" />
                            </photos>
                        </rsp>""")
        self.proxy.photos_recentlyUpdated.mock_returns = photos_xml

        self.hit_cb = False

        def _cb(state, meta):
            self.hit_cb = True

            assert state == 'update', state
            assert meta == (1, 1), meta

        assert '2717638353' in self.index.refresh(progress_callback=_cb)
        assert self.hit_cb

    @raises(FlickrError)
    def test_refresh_fail_response(self):
        """Failed refresh from Flickr"""

        photos_xml = XML("""
                         <rsp stat="fail">
                            <err code="1234" msg="Test Message" />
                         </rsp>""")
        self.proxy.photos_recentlyUpdated.mock_returns = photos_xml

        assert not self.index.refresh()

    def _run_scripted_test(self, test):
        """Helper function to run a scripted doctest"""

        script = (XML(p) for p in doctest.DocTestParser().parse(test._dt_test.docstring)
                  if isinstance(p, str) and p.strip())

        self.proxy.photos_recentlyUpdated.mock_returns = None
        self.proxy.photos_recentlyUpdated.mock_returns_iter = script

        self.index.refresh()

        test._dt_test.globs['index'] = self.index
        test._dt_test.globs['proxy'] = self.proxy
        test.runTest()

    def test_load_scripted(self):
        """Generated test simulating Flickr metadata"""

        for fn in glob.glob(os.path.join(DATA, 'scripts') + '/*.txt'):
            dt = doctest.DocFileTest(fn, module_relative=False)
            yield self._run_scripted_test, dt


class IndexTests: #(unittest.TestCase):
    """Flickr Index API tests."""

    def setUp(self):
        self.proxy = Mock('FlickrAPI')
        self.index_fn = tempfile.mktemp()  # OK to use as we're just testing...
        self.index = FlickrIndex(self.proxy, filename=self.index_fn)

    def tearDown(self):
        minimock.restore()
        os.remove(self.index_fn)

    def test_add_ok(self):
        """Add a shorthash to an index."""

        p = {'id': '1234', 'lastupdate': '987654321'}
        self.index.add(repr(p), p)

        assert repr(p) in self.index
        assert self.index[repr(p)] == (p['id'], int(p['lastupdate']))

    @raises(ValueError)
    def test_add_bad_time(self):
        """Add a shorthash with a bad timestamp."""

        p = {'id': '1234', 'lastupdate': 'abc123'}
        self.index.add(repr(p), p)

    def test_add_duplicate(self):
        """Adding colliding shorthashes."""

        p1 = {'id': '1234', 'lastupdate': '987654321'}
        self.index.add('hash', p1)

        assert self.index['hash'] == (p1['id'], int(p1['lastupdate']))

        p2 = {'id': '1235', 'lastupdate': '289123894'}
        self.index.add('hash', p2)

        assert self.index['hash'] == (p2['id'], int(p2['lastupdate']))

class IndexRefreshTests: #(unittest.TestCase):
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
    
    @raises(FlickrError)
    def test_refresh_failure(self):
        """Failed update from Flickr"""

        photos = [
            {'id': '1'},
            {'id': '2'},
            {'id': '3'},
        ]

        def slicer(ps):
            return [p['id'] for p in ps]

        minimock.mock('pif.flickr.recent_photos', returns=photos)
        minimock.mock('pif.flickr.get_photos_shorthashes', returns=(slicer(photos[:-1]), slicer(photos[-1:])))

        self.index.refresh()

class ShorthashTests: #(unittest.TestCase):
    """Shorthash retrieval tests."""

    def tearDown(self):
        minimock.restore()

    def test_url_valid(self):
        """URL for Flickr photos"""

        p = {
            'farm': '[farmID]',
            'server': '[serverID]',
            'id': '123456789',
            'originalsecret': '[secretID]',
            'originalformat': 'jpg',
            'o_width': '128',
            'o_height': '256',
        }

        response = Mock('PhotoRequest')
        response.code = 206
        response.headers = {'content-range': '0-512/56789'}
        response.read.mock_returns = 'somerandomcrap'

        def _(url):
            assert url.get_full_url() == 'http://farm[farmID].static.flickr.com/[serverID]/123456789_[secretID]_o.jpg', url.get_full_url()
            return response

        urlopen = minimock.mock('urllib2.urlopen', returns_func=_)

        sh = get_photo_shorthash(p)

        assert sh
        assert isinstance(sh, str)

    @raises(FlickrError)
    def test_complete(self):
        """Wrong status from Flickr for photo"""

        p = {
            'farm': '[farmID]',
            'server': '[serverID]',
            'id': '[idID]',
            'originalsecret': '[secretID]',
            'originalformat': 'jpg',
            'o_width': '128',
            'o_height': '256',
        }

        response = Mock('PhotoRequest')
        response.code = 200
        urlopen = minimock.mock('urllib2.urlopen', returns=response)
        
        get_photo_shorthash(p)

    def test_shorthashes_failure(self):
        """Failure in shorthash batch retrieval."""

        photos = [
            {'id': '1'},
            {'id': '2'},
            {'id': '3'},
        ]

        def _(photo):
            if photo['id'] == '2': raise FlickrError

            return 'hash' + photo['id']

        minimock.mock('pif.flickr.get_photo_shorthash', returns_func=_)

        shs, fails = get_photos_shorthashes(photos)

        assert shs and fails

        for pid in [p['id'] for p in photos]:
            assert pid in shs or pid in fails, pid

    def test_shorthashes_cb(self):
        """Callback from getting shorthashes"""

        photos = [
            {'id': '1'},
        ]

        def _(photo):
            return 'hash' + photo['id']

        minimock.mock('pif.flickr.get_photo_shorthash', returns_func=_)

        self.hit_cb = False

        def _cb(state, meta):
            self.hit_cb = True

            assert state == 'index', state
            assert meta == (1, 1), meta

        assert get_photos_shorthashes(photos, progress_callback=_cb)
        assert self.hit_cb
