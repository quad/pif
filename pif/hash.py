import urllib2

import threadpool

import pif
import pif.dictdb

from pif import TAILHASH_SIZE, make_shorthash


class HashIndex(pif.dictdb.DictDB):
    """Cache for photo shorthashes."""

    RETRIES = 3
    THREADS = 4

    def __init__(self, photos, filename):
        pif.dictdb.DictDB.__init__(self, filename)

        self.photos = photos


    def _get_shorthash(self, photo_id):
        """Get a shorthash for a Flickr photo."""

        photo = self.photos[photo_id]

        req = urllib2.Request(
            url=photo['url_o'],
            headers={'Range': "bytes=-%u" % TAILHASH_SIZE},
        )

        f = urllib2.urlopen(req)

        if f.code != urllib2.httplib.PARTIAL_CONTENT:
            raise IOError("Got status %s from Flickr" % f.code)

        return make_shorthash(
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
        pool = threadpool.ThreadPool(self.THREADS)
        for retry in xrange(self.RETRIES):
            def _results_cb(request, result):
                shorthashes[request.args[0]] = result

                if progress_callback:
                    progress_callback(
                        'hashes', (len(shorthashes), len(photo_ids))
                    )

            def _exception_cb(request, exc_info):
                t, v, tb = exc_info

                if not issubclass(t, IOError):
                    raise t, v, tb

            reqs = threadpool.makeRequests(
                self._get_shorthash,
                photo_ids - set(shorthashes),
                _results_cb,
                _exception_cb
            )
            [pool.putRequest(r) for r in reqs]
            pool.wait()

            if len(shorthashes) == len(photo_ids):
                break

        pool.dismissWorkers(len(pool.workers))

        if photo_ids - set(shorthashes):
            raise IOError('Could not retrieve all shorthashes')

        return shorthashes


    def _merge_shorthashes(self, photo_shorthashes):
        """Returns an update representing a merge of the passed shorthashes."""

        # Invert the hash index to check for photo ID collisions.
        inverted = {}
        for sh, pids in self.iteritems():
            for p in pids:
                assert p not in inverted
                inverted[p] = sh

        # Merge the new shorthashes.
        merged_shorthashes = set()
        for pid, sh in photo_shorthashes.iteritems():
            # If a photo ID is replaced, remove the original owning shorthash.
            if pid in inverted:
                sh_old = inverted[pid]

                if sh == sh_old:
                    continue
                else:
                    self[sh_old].remove(pid)
                    merged_shorthashes.add(sh_old)

            self.setdefault(sh, []).append(pid)
            merged_shorthashes.add(sh)

        return merged_shorthashes


    def refresh(self, progress_callback=None):
        assert self.photos is not None, 'Refresh with no metadata?'

        photo_ids = set(self.photos.refresh(progress_callback))
        photo_shorthashes = self._get_shorthashes(photo_ids, progress_callback)
        new_shorthashes = self._merge_shorthashes(photo_shorthashes)

        return list(new_shorthashes)
