import os
import random
import sys
import tempfile
import urllib2

import minimock

from minimock import Mock
from nose.tools import raises

import pif

from pif.flickr import FlickrError
from pif.hash import HashIndex

from tests.mock import MockDict

class TestHashIndex:
    """Flickr Shorthash Index API tests."""

    def setUp(self):
        self.photos = MockDict('PhotoIndex')
        self.photos.refresh.mock_returns = []

        self.index_fn = tempfile.mktemp()  # OK to use as we're just testing...
        self.index = HashIndex(self.photos, filename=self.index_fn)

        self.urls = {}
        minimock.mock('urllib2.urlopen', returns_func=self._mock_urlopen)

        self.tails = {}
        minimock.mock('pif.make_shorthash', returns_func=self._mock_shorthash)

    def _mock_urlopen(self, request):
        # TODO: Run assertions on argument validity.
        return self.urls[request.get_full_url()]


    def _mock_shorthash(self, tail, original_format, size, width, height):
        # TODO: Run assertions on argument validity.
        return self.tails[tail]


    def make_mock_photo(self, photo_id):
        r = random.Random(photo_id)

        format = r.choice(('jpg', 'gif', 'png'))
        h, w, s = map(r.randint, (1, 1, 512), (5000, 5000, sys.maxint))
        url = "http://test_%s_o.%s" % (photo_id, format)

        # The PhotoIndex refresh gives a photo ID.
        self.photos.refresh.mock_returns.append(photo_id)

        # The fake photo ID points at the PhotoIndex record.
        self.photos[photo_id] = {
            'id': photo_id,
            'originalformat': format,
            'o_height': str(h),
            'o_width': str(w),
            'size': str(s),
            'url_o': url,
        }

        # The record's URL points at the request.
        tail = 'tail data' + photo_id

        request = Mock("Request(%s)" % url)
        request.code = urllib2.httplib.PARTIAL_CONTENT
        request.headers = {'content-range': "%u-%u/%u" % (s - 512, s, s)}
        request.read.mock_returns = tail

        self.urls[url] = request

        # The tail data points at the fake shorthash.
        shorthash = 'short hash' + photo_id

        self.tails[tail] = shorthash

        return shorthash

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

    def test_refresh_no_cb(self):
        """HashIndex refresh with no callback"""

        sh = self.make_mock_photo('123')

        assert self.index.refresh() == [sh]

    def test_refresh_cb(self):
        """Callback from HashIndex refresh"""

        sh = self.make_mock_photo('123')

        self.hit_cb = False

        def _cb(state, meta):
            self.hit_cb = True

            assert state == 'hashes', state
            assert meta == (1, 1), meta

        assert self.index.refresh(progress_callback=_cb) == [sh]

        assert self.hit_cb

    @raises(FlickrError)
    def test_refresh_failure(self):
        """Failed update from Flickr"""

        self.photos.refresh.mock_raises = FlickrError

        self.index.refresh()

    @raises(IOError)
    def test_complete(self):
        """Wrong status from Flickr for photo download"""

        self.make_mock_photo('123')
        self.urls.values()[0].code = 404

        self.index.refresh()

    @raises(IOError)
    def test_get_fail(self):
        """Fail shorthash retrieval"""

        self.make_mock_photo('123')

        minimock.mock('urllib2.urlopen', raises=IOError)

        self.index.refresh()

    def test_get_fail_intermittent(self):
        """Fail shorthash retrieval twice."""

        sh = self.make_mock_photo('123')

        fails = []
        old_open = urllib2.urlopen
        def _(request):
            fails.append(True)

            if len(fails) < 3:
                raise IOError()
            else:
                return old_open(request)

        minimock.mock('urllib2.urlopen', returns_func=_)

        assert self.index.refresh() == [sh]

    def test_multiple_photos(self):
        """HashIndex refresh with a lot of unique photos"""

        shs = [self.make_mock_photo(str(pid)) for pid in xrange(200)]

        assert set(self.index.refresh()) == set(shs)

        for pid, sh in enumerate(shs):
            assert self.index[sh] == [str(pid)]

    def test_duplicate_shorthashes(self):
        """Duplicate shorthashes"""

        self.make_mock_photo('123')
        self.make_mock_photo('321')

        sh = 'collision'

        for k in self.tails:
            self.tails[k] = sh

        assert self.index.refresh() == [sh]
        assert set(self.index[sh]) == set(['123', '321'])
