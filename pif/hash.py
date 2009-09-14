import collections
import shelve
import threadpool
import urllib2

import pif

from pif.flickr import FlickrError


class HashIndex(object, shelve.DbfilenameShelf):
    """Cache for photo shorthashes."""

    def __init__(self, photos, filename):
        shelve.DbfilenameShelf.__init__(self, filename)

        self.photos = photos


    def _get_shorthash(self, photo):
        """Get a shorthash for a Flickr photo."""

        req = urllib2.Request(
            url=photo['url_o'],
            headers={'Range': "bytes=-%u" % pif.TAILHASH_SIZE},
        )

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


#     def __get_photos_shorthashes(self, photos, progress_callback=None):
#        """Get shorthashes for Flickr photos."""
#
#        NUM_WORKERS = 4
#
#        failures = []
#        processed_photos = []
#        shorthashes = collections.defaultdict(list)
#
#        def _cb(request, result):
#            sh, (p, ) = result, request.args
#            pid = p['id']
#
#            shorthashes[pid].append(sh)
#            processed_photos.append(pid)
#
#            if progress_callback:
#                progress_callback('hashes', (len(processed_photos), len(photos)))
#
#        def _ex(request, exc_info):
#            (p, ) = request.args
#            failures.append(p['id'])
#
#        pool = threadpool.ThreadPool(NUM_WORKERS)
#
#        for req in threadpool.makeRequests(self.__get_photo_shorthash, photos, _cb, _ex):
#            pool.putRequest(req)
#
#        pool.wait()
#        pool.dismissWorkers(len(pool.workers))
#
#        return shorthashes, failures


    def refresh(self, progress_callback=None):
        assert self.photos is not None, 'Refresh with no metadata?'

        photos = self.photos.refresh()

        shorthashes = []
        for p in photos:
            shorthashes.append(self._get_shorthash(self.photos[p]))
            
            if progress_callback:
                progress_callback('hashes', (len(shorthashes), len(photos)))

        return shorthashes
