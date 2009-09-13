import logging
import shelve

from xml.parsers.expat import ExpatError

import flickrapi
import pkg_resources

from flickrapi.exceptions import FlickrError

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
                progress_callback('photos', (page, pages))

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
