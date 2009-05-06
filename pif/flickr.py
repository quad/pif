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


def recent_photos(proxy, min_date=1, progress_callback=None):
    """An iterator of the recently updated photos."""

    page, pages = 1, 1

    while page <= pages:
        resp = proxy.photos_recentlyUpdated(
            page=page,
            min_date=min_date,
            extras='o_dims, original_format, last_update',
        )

        photos = resp.find('photos')

        if photos:
            for photo in photos.findall('photo'):
                yield photo.attrib
        else:
            break

        pages = int(photos.get('pages'))

        if progress_callback:
            progress_callback('update', (page, pages))

        page = int(photos.get('page')) + 1


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

    last_update = property(lambda self: max([0, ] + [lu for id, lu in self.values()]))
