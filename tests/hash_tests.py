import os
import tempfile
import urllib2

import minimock

from minimock import Mock
from nose.tools import raises

import pif

from pif.hash import FlickrError, HashIndex

class TestHashIndex:
    """Flickr Shorthash Index API tests."""

    def setUp(self):
        self.photos = Mock('PhotoIndex')
        self.photos.refresh.mock_results = []

        self.index_fn = tempfile.mktemp()  # OK to use as we're just testing...
        self.index = HashIndex(self.photos, filename=self.index_fn)

        self.urls_requested = []
        self.urls_ok = []
        minimock.mock('urllib2.urlopen') #, returns_func=self._mock_urlopen)

        minimock.mock('pif.make_shorthash') #, returns_func=self._mock_shorthash)

    def _mock_urlopen(self, request):
        self.urls_requested.append(request.url)

        assert request.url in self.urls_ok

    def _mock_shorthash(self, tail, original_format, size, width, height):
        pass

    def _make_mock_photo(self, photo_id=None):
        if not photo_id:
            photo_id = str(random.randint(0, sys.maxint))

        format = random.choice('jpg', 'gif', 'png')
        h, w, s = map(random.randint, ((1, 5000), (1, 5000), (1, sys.maxint)))
        url = "http://test_%s_o.%s" % (photo_id, format)

        self.photos.refresh.mock_returns.append(photo_id)
        self.photos.mock_attrs[photo_id] = {
            'id': photo_id,
            'originalformat': format,
            'o_height': str(h),
            'o_width': str(w),
            'size': str(s),
            'url_o': url,
        }

        self.urls_ok.append(url)

        return 'fakeSH' + photo_id

    def tearDown(self):
        minimock.restore()
        os.remove(self.index_fn)
    
    def test_init_no_photo_index(self):
        """Initialize HashIndex without metadata"""

        i = HashIndex(None, self.index_fn)

        assert i is not None

    @raises(AssertionError)
    def test_refresh_fail_no_photo_index(self):
        """HashIndex refresh fails without metadata"""

        self.index.photos = None
        self.index.refresh()

    def test_refresh_empty(self):
        """An empty HashIndex refresh"""

        assert self.index.refresh() == []
        assert not self.urls_requested

    def test_refresh_no_cb(self):
        """HashIndex refresh with no callback"""

        pid = self._mock_photo()

        assert self.index.refresh() == [pid]
        assert len(self.urls_requested) == 1

    def test_refresh_cb(self):
        """Callback from HashIndex refresh"""

        pid = self._mock_photo()

        self.hit_cb = False

        def _cb(state, meta):
            self.hit_cb = True

            assert state == 'hashes', state
            assert meta == (1, 1), meta

        assert self.index.refresh(progress_callback=_cb) == [pid]
        assert len(self.urls_requested) == 1

        assert self.hit_cb

    @raises(FlickrError)
    def test_refresh_failure(self):
        """Failed update from Flickr"""

        del self.photos.refresh.mock_results
        self.photos.refresh.mock_raises = FlickrError

        self.index.refresh()

    @raises(FlickrError)
    def test_complete(self):
        """Wrong status from Flickr for photo download"""

    def test_shorthashes_failure(self):
        """Failure in shorthash batch retrieval"""
