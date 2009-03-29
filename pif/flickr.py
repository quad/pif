import logging
import shelve
import threadpool

import flickrapi
import httplib2
import pkg_resources

from flickrapi.exceptions import FlickrError

import pif

LOG = logging.getLogger(__name__)

API_KEY, API_SECRET = pkg_resources.resource_string(__name__, 'flickr-api.key').split()

def get_proxy(key=API_KEY, secret=API_SECRET, wait_callback=None):
    # Setup the API proxy.
    proxy = flickrapi.FlickrAPI(key, secret, format='etree')

    # Authorize.
    auth_response = proxy.get_token_part_one(perms='write')

    while True:
        try:
            if proxy.get_token_part_two(auth_response):
                break
        except FlickrError, e:
            # Wait for frob confirmation.
            if 'Error: 108' in e.message and \
               wait_callback and not wait_callback():
                continue
            raise

    return proxy

class FlickrIndex(object, shelve.DbfilenameShelf):
    NUM_WORKERS = 4

    def __init__(self, proxy, filename):
        shelve.DbfilenameShelf.__init__(self, filename)

        self.proxy = proxy

    def add(self, shorthash, id):
        if shorthash in self:
            if id not in self[shorthash]:
                self[shorthash] += (id,)
        else:
            self[shorthash] = (id,)

    def refresh(self, progress_callback=None):
        if self.proxy:
            new_photos, last_update = self._refresh_updated(progress_callback)
            self._refresh_sizes(new_photos, progress_callback)

            self.last_update = last_update

    def _refresh_updated(self, progress_callback):
        """Synchronize to the recently updated photos."""

        def recent_pages(*args, **kwargs):
            """An iterator of the recent updated photo pages."""

            page, pages = 1, 1
            while page <= pages:
                if progress_callback:
                    progress_callback('update', (page, pages))

                photos = self.proxy.photos_recentlyUpdated(page=page, *args, **kwargs).find('photos')

                if photos: yield photos
                else: break

                page = int(photos.get('page')) + 1
                pages = int(photos.get('pages'))

        # Pull down the index of updated photos.
        photo_pages = recent_pages(extras='o_dims, original_format, last_update',
                                   min_date=self.last_update + 1)

        # Create records for the photos.
        new_photos = []
        last_update = self.last_update

        for photo_page_num, photo_page in enumerate(photo_pages):
            for photo_xml in photo_page.findall('photo'):
                new_photos.append(photo_xml.attrib)

                last_update = max(last_update, int(photo_xml.attrib['lastupdate']))

        return new_photos, last_update

    def _url(self, photo):
        return "http://farm%s.static.flickr.com/%s/%s_%s_o.%s" % \
                (photo['farm'],
                 photo['server'],
                 photo['id'],
                 photo['originalsecret'],
                 photo['originalformat'])

    def _refresh_sizes(self, new_photos, progress_callback):
        def get_photo_size(photo):
            # TODO: Persist the HTTP connection.
            h = httplib2.Http()

            resp, content = h.request(uri=self._url(photo),
                                      headers={'Range': "bytes=-%u" % pif.TAILHASH_SIZE})
            assert resp.status == 206

            shorthash = pif.make_shorthash(
                content,
                photo['originalformat'],
                int(resp['content-range'].split('/')[-1]),
                int(photo['o_width']),
                int(photo['o_height']),
            )
            
            return shorthash, int(photo['id'])

        if progress_callback:
            self.__processed_photos = 0

        def add_photo(request, result):
            if progress_callback:
                progress_callback('index', (self.__processed_photos, len(new_photos)))
                self.__processed_photos += 1

            self.add(*result)

        requests = threadpool.makeRequests(
            get_photo_size,
            new_photos,
            add_photo
        )

        if requests:
            pool = threadpool.ThreadPool(0)

            for r in requests:
                pool.putRequest(r)

            pool.createWorkers(self.NUM_WORKERS, poll_timeout=0)
            pool.wait()

            pool.dismissWorkers(len(pool.workers))

    def _get_last_update(self):
        if self.has_key('last_update'):
            return self['last_update']
        else:
            return 1    # Use 1 as Flickr ignores 0.

    def _set_last_update(self, value):
        self['last_update'] = value

    last_update = property(_get_last_update, _set_last_update)
