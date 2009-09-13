import collections
import logging
import shelve
import threadpool
import urllib2

from xml.parsers.expat import ExpatError

import flickrapi
import pkg_resources

from flickrapi.exceptions import FlickrError

import pif

LOG = logging.getLogger(__name__)

API_KEY, API_SECRET = pkg_resources.resource_string(__name__, 'flickr-api.key').split()


def get_proxy(key=API_KEY, secret=API_SECRET, wait_callback=None):
    """Get a web service proxy to Flickr."""

    # Setup the API proxy.
    proxy = flickrapi.FlickrAPI(key, secret, format='etree')

    try:
        # Authorize.
        auth_response = proxy.get_token_part_one(perms='write')
    except ExpatError:    # FlickrAPI chokes on non-XML responses.
        raise FlickrError('Non-XML response from Flickr')

    while True:
        try:
            if proxy.get_token_part_two(auth_response):
                break
        except FlickrError as e:
            # Wait for frob confirmation.
            frob_ok = filter(lambda x: x.startswith('Error: 108'), e)
            if frob_ok and wait_callback and not wait_callback():
                continue
            raise

    return proxy


class PhotoIndex(object, shelve.DbfilenameShelf):
    """A cache for Flickr photostream metadata."""

    last_update = property(lambda self: max([0, ] + [int(p['lastupdate']) for p in self.itervalues()]))

    def __init__(self, proxy, filename):
        shelve.DbfilenameShelf.__init__(self, filename)

        self.proxy = proxy

    def _iter_recent(self, progress_callback=None):
        """Get the recently updated photos."""

        page, pages = 1, 1

        while page <= pages:
            resp = self.proxy.photos_recentlyUpdated(
                page=page,
                min_date=self.last_update + 1,
                extras=', '.join((
                    'date_upload',
                    'last_update',
                    'o_dims',
                    'original_format',
                    'url_o',
                ))
            )

            photos = resp.find('photos')

            if photos:
                for photo in photos.findall('photo'):
                    yield photo.attrib
            elif photos is None:
                raise FlickrError('No photos in server response.')
            else:
                break

            pages = int(photos.get('pages'))

            if progress_callback:
                progress_callback('update', (page, pages))

            page = int(photos.get('page')) + 1

    def refresh(self, progress_callback=None):
        assert self.proxy, "Refresh with no proxy?"

        # TODO: Detect deleted photos.
        recent_photos = list(self._iter_recent(progress_callback))

        # Only new or replaced photos count as updated.
        def _(new_p, old_p):
            return not old_p or new_p['dateupload'] != old_p['dateupload']
        
        updated_photos = [p['id'] for p in recent_photos if _(p, self.get(p['id']))]

        # Update the index.
        self.update(((p['id'], p) for p in recent_photos))

        return updated_photos


def get_photo_shorthash(photo):
    """Get a shorthash for a Flickr photo."""

    req = urllib2.Request(
        url="http://farm%s.static.flickr.com/%s/%s_%s_o.%s" % (
            photo['farm'],
            photo['server'],
            photo['id'],
            photo['originalsecret'],
            photo['originalformat']),
        headers={'Range': "bytes=-%u" % pif.TAILHASH_SIZE})

    f = urllib2.urlopen(req)

    if f.code != urllib2.httplib.PARTIAL_CONTENT:
        raise FlickrError("Got status %s from Flickr" % f.code)

    return pif.make_shorthash(
        f.read(),
        photo['originalformat'],
        int(f.headers['content-range'].split('/')[-1]),
        int(photo['o_width']),
        int(photo['o_height']),
    )


def get_photos_shorthashes(photos, progress_callback=None):
    """Get shorthashes for Flickr photos."""

    NUM_WORKERS = 4

    failures = []
    processed_photos = []
    shorthashes = collections.defaultdict(list)

    def _cb(request, result):
        sh, (p, ) = result, request.args
        pid = p['id']

        shorthashes[pid].append(sh)
        processed_photos.append(pid)

        if progress_callback:
            progress_callback('index', (len(processed_photos), len(photos)))

    def _ex(request, exc_info):
        (p, ) = request.args
        failures.append(p['id'])

    pool = threadpool.ThreadPool(NUM_WORKERS)

    for req in threadpool.makeRequests(get_photo_shorthash, photos, _cb, _ex):
        pool.putRequest(req)

    pool.wait()
    pool.dismissWorkers(len(pool.workers))

    return shorthashes, failures


class FlickrIndex(object, shelve.DbfilenameShelf):
    """Cache for Flickr photo shorthashes."""

    STUB = (None, 0)

    def __init__(self, proxy, filename):
        shelve.DbfilenameShelf.__init__(self, filename)

        self.proxy = proxy

    def add(self, shorthash, photo):
        entry = photo['id'], int(photo['lastupdate'])

        if shorthash in self:
            old_sh = self[shorthash]
            if old_sh != self.STUB and old_sh != entry:
                LOG.warning("Shorthash collision: %s on %s" % (entry, old_sh))

        self[shorthash] = entry

    def ignore(self, shorthash):
        if shorthash not in self:
            self[shorthash] = self.STUB

    def refresh(self, progress_callback=None):
        if self.proxy:
            photos = list(recent_photos(self.proxy, self.last_update + 1, progress_callback))
            shorthashes, failures = get_photos_shorthashes(photos, progress_callback)

            if failures:
                raise FlickrError("Shorthash retrieval failures: %s" % \
                                  ', '.join(failures))

            for p in photos:
                for sh in shorthashes[p['id']]:
                    self.add(sh, p)
