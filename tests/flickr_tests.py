import glob
import os
import os.path
import tempfile

from doctest import DocFileTest, DocTestParser
from xml.etree.ElementTree import XML
from xml.parsers.expat import ExpatError

import flickrapi
import minimock

from minimock import Mock
from nose.tools import assert_raises, raises

from pif.flickr import FlickrError, PhotoIndex, get_proxy

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

        minimock.mock('flickrapi.FlickrAPI.get_token_part_one',
                      raises=ExpatError)

        get_proxy()

    @raises(FlickrError)
    def test_reject(self):
        """Rejected proxy"""

        minimock.mock('flickrapi.FlickrAPI.get_token_part_one')
        minimock.mock('flickrapi.FlickrAPI.get_token_part_two',
                      raises=FlickrError)

        get_proxy()

    def test_ok(self):
        """OK proxy"""

        minimock.mock('flickrapi.FlickrAPI.get_token_part_one')
        minimock.mock('flickrapi.FlickrAPI.get_token_part_two', returns=True)

        assert isinstance(get_proxy(), flickrapi.FlickrAPI)

    def test_cb(self):
        """Callback from proxy"""

        minimock.mock('flickrapi.FlickrAPI.get_token_part_one', returns=('token', 'frob'))

        def _bad_api(auth_response):
            raise FlickrError('Error: 108: Invalid frob')

        minimock.mock('flickrapi.FlickrAPI.get_token_part_two',
                      returns_func=_bad_api)

        self.hit_cb = False

        def _cb(proxy, perms, token, frob):
            assert perms == 'write'
            assert token == 'token'
            assert frob == 'frob'

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

            assert state == 'photos', state
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

        script = (XML(p)
                  for p in DocTestParser().parse(test._dt_test.docstring)
                  if isinstance(p, str) and p.strip())

        self.proxy.photos_recentlyUpdated.mock_returns = None
        self.proxy.photos_recentlyUpdated.mock_returns_iter = script

        _ = self.index.refresh()

        test._dt_test.globs['_'] = _
        test._dt_test.globs['index'] = self.index
        test._dt_test.globs['proxy'] = self.proxy
        test.runTest()

    def test_load_scripted(self):
        """Generated test simulating Flickr metadata"""

        for fn in glob.glob(os.path.join(DATA, 'scripts') + '/*.txt'):
            dt = DocFileTest(fn, module_relative=False)
            yield self._run_scripted_test, dt
