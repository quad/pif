import hashlib
import logging
import threadpool
import time

import flickrapi
import httplib2
import pkg_resources

API_KEY, API_SECRET = pkg_resources.resource_string(__name__, 'flickr-api.key').split()

def _default_proxy_cb():
    logging.info('Waiting for authorization from Flickr...')
    time.sleep(5)

def get_proxy(key=API_KEY, secret=API_SECRET, wait_callback=_default_proxy_cb):
    # Setup the API proxy.
    proxy = flickrapi.FlickrAPI(key, secret, format = 'etree')

    # Authorize.
    auth_response = proxy.get_token_part_one(perms = 'write')

    while True:
        try:
            if proxy.get_token_part_two(auth_response):
                break
        except flickrapi.exceptions.FlickrError, e:
            # Wait for frob confirmation.
            if 'Error: 108' in e.message and not wait_callback():
                continue
            raise

    return proxy

class FlickrPhoto:
    TAILHASH_SIZE = 512

    def __init__(self, id):
        self.id = id

    def _get_url(self):
        return "http://farm%s.static.flickr.com/%s/%s_%s_o.%s" % \
                (self.farm,
                 self.server,
                 self.id,
                 self.original_secret,
                 self.original_format)

    url = property(_get_url)

class FlickrIndex:
    NUM_WORKERS = 4

    def __init__(self, proxy):
        self.proxy = proxy
        self.last_update = 1
        self.photos = {}

    def refresh(self):
        new_photos = self.refresh_updated()
        self.refresh_sizes(new_photos)

    def refresh_updated(self):
        """Synchronize to the recently updated photos."""

        def recent_pages(*args, **kwargs):
            """An iterator of the recent updated photo pages."""

            page, pages = 1, 1
            while page <= pages:
                photos = self.proxy.photos_recentlyUpdated(page=page, *args, **kwargs).find('photos')

                if photos: yield photos
                else: break

                page = int(photos.get('page')) + 1
                pages = int(photos.get('pages'))

        # Pull down the index of updated photos.
        photo_pages = recent_pages(extras='o_dims, original_format, last_update',
                                   min_date=self.last_update)

        # Create records for the photos.

        new_photos = []

        for photo_page_num, photo_page in enumerate(photo_pages):
            for photo_xml in photo_page.findall('photo'):
                pid = int(photo_xml.attrib['id'])
                last_update = int(photo_xml.attrib['lastupdate'])

                # Only update if there has been changes.
                
                if self.photos.has_key(pid):
                    p = self.photos[pid]
                    
                    if p.last_update == last_update:
                        continue
                else:
                    p = FlickrPhoto(pid)
                    self.photos[p.id] = p

                p.last_update = last_update

                p.original_format = photo_xml.attrib['originalformat']
                p.original_secret = photo_xml.attrib['originalsecret']

                p.farm = int(photo_xml.attrib['farm'])
                p.server = int(photo_xml.attrib['server'])

                p.height = int(photo_xml.attrib['o_height'])
                p.width = int(photo_xml.attrib['o_width'])

                self.last_update = max(self.last_update, int(photo_xml.attrib['lastupdate']))

                new_photos.append(p)

        return new_photos

    def refresh_sizes(self, new_photos):
        def get_photo_size(photo):
            # TODO: Persist the HTTP connection.
            h = httplib2.Http()

            resp, content = h.request(uri = photo.url,
                                      headers = {'Range': "bytes=-%u" % FlickrPhoto.TAILHASH_SIZE})
            assert resp.status == 206

            photo.size = int(resp['content-range'].split('/')[-1])
            photo.tailhash = hashlib.sha512(content).hexdigest()

        requests = [threadpool.WorkRequest(get_photo_size, (p, ))
                    for p in new_photos]

        if requests:
            pool = threadpool.ThreadPool(self.NUM_WORKERS)

            for r in requests:
                pool.putRequest(r)
            pool.wait()

            pool.dismissWorkers(self.NUM_WORKERS)
