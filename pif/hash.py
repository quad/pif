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


    def _get_shorthashes(self, photo_ids, progress_callback):
        """Get shorthashes for multiple Flickr photos."""

        shorthashes = {}

        # Threadpool the retrieval of the photo shorthashes, retrying the
        # process on aborted photos.
        pool = multiprocessing.Pool()
        for retry in xrange(self.RETRIES):
            def _results_cb(results):
                shorthashes.update(results)

                # TODO: Progress callback on a per-item basis.
                if progress_callback:
                    progress_callback(
                        'hashes', (len(shorthashes), len(photo_ids))
                    )

            map_results = pool.map_async(
                lambda pid: (pid, self._get_shorthash(pid)),
                photo_ids - set(shorthashes),
                callback=_results_cb,
            )
            map_results.wait()

            if map_results.successful():
                break

        if photo_ids - set(shorthashes):
            raise IOError('Could not retrieve all shorthashes')

        return shorthashes


    def _merge_shorthashes(self, photo_shorthashes):
        """Returns an update representing a merge of the passed shorthashes."""

        # If a photo IDs is to be replaced, copy across the owning shorthash
        # sans it.
        results = {}
        for sh, pids in self.iteritems():
            for p in set(pids) & set(photo_shorthashes):
                results.setdefault(sh, self[sh]).remove(p)

        # Merge the new shorthashes.
        for pid, sh in photo_shorthashes.iteritems():
            results.setdefault(sh, self.get(sh, [])).append(pid)

            # Don't make unnecessary updates.
            if results[sh] == self.get(sh, []):
                del results[sh]

        return results


    def refresh(self, progress_callback=None):
        assert self.photos is not None, 'Refresh with no metadata?'

        photo_ids = set(self.photos.refresh(progress_callback))
        photo_shorthashes = self._get_shorthashes(photo_ids, progress_callback)
        new_shorthashes = self._merge_shorthashes(photo_shorthashes)

        self.update(new_shorthashes)

        return new_shorthashes.keys()
