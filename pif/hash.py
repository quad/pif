import multiprocessing.dummy as multiprocessing  # <3 threads
import shelve
import urllib2

import pif


class HashIndex(object, shelve.DbfilenameShelf):
    """Cache for photo shorthashes."""

    RETRIES = 3

    def __init__(self, photos, filename):
        shelve.DbfilenameShelf.__init__(self, filename)

        self.photos = photos


    def _get_shorthash(self, photo_id):
        """Get a shorthash for a Flickr photo."""

        photo = self.photos[photo_id]

        req = urllib2.Request(
            url=photo['url_o'],
            headers={'Range': "bytes=-%u" % pif.TAILHASH_SIZE},
        )

        f = urllib2.urlopen(req)

        if f.code != urllib2.httplib.PARTIAL_CONTENT:
            raise IOError("Got status %s from Flickr" % f.code)

        return pif.make_shorthash(
            f.read(),
            photo['originalformat'],
            int(f.headers['content-range'].split('/')[-1]),
            int(photo['o_width']),
            int(photo['o_height']),
        )


    def refresh(self, progress_callback=None):
        assert self.photos is not None, 'Refresh with no metadata?'

        photo_ids = self.photos.refresh()

        # Threadpool the retrieval of the photo shorthashes, retrying the
        # process on aborted photos.
        pool = multiprocessing.Pool()
        shorthashes = {}
        for retry in xrange(self.RETRIES):
            def _track_cb(results):
                for pid, sh in results:
                    shorthashes[pid] = sh
                    photo_ids.remove(pid)

                if progress_callback:
                    progress_callback(
                        'hashes', (len(shorthashes),
                                   len(photo_ids) + len(shorthashes))
                    )

            map_results = pool.map_async(
                lambda pid: (pid, self._get_shorthash(pid)),
                set(photo_ids) - set(shorthashes),
                callback=_track_cb,
            )
            map_results.wait()

            if map_results.successful():
                break

        if photo_ids:
            raise IOError('Could not retrieve all shorthashes')

        # Merge the shorthashes and photo IDs.
        retval = set()
        for pid, sh in shorthashes.iteritems():
            self[sh] = self.get(sh, []) + [pid, ]
            retval.add(sh)

        return list(retval)
