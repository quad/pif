import logging
import time

from pif.ui import OPTIONS, common_run

LOG = logging.getLogger(__name__)

def proxy_callback():
    LOG.info('Waiting for authorization from Flickr...')
    time.sleep(5)

def progress_callback(state, meta):
    msgs = {
        'update': 'Loading updates from Flickr...',
        'index': 'Indexing photos on Flickr...',
    }

    a, b = meta
    LOG.info("%s (%u / %u)" % (msgs[state], a, b))

def run():
    OPTIONS.add_option('-m', '--mark', action='store_true',
                       help='mark files as uploaded')
    options, args = OPTIONS.parse_args()

    indexes, images = common_run((options, args), proxy_callback, progress_callback)
    file_index, flickr_index = indexes

    if options.mark:
        LOG.info('Marked as uploaded:')
        for fn in images:
            if not options.dry_run:
                flickr_index.ignore(file_index[fn])

            LOG.info("\t%s" % fn)
    else:
        for fn in images:
            def _(progress, done):
                if done:
                    LOG.info("Uploaded %s" % fn)
                else:
                    LOG.debug("Uploading %s... (%s%%)" % (fn, progress))

            if options.dry_run:
                LOG.info("Uploaded %s" % fn)
            else:
                flickr_index.proxy.upload(filename=fn, callback=_)

    file_index.close()

    if not options.dry_run:
        flickr_index.close()
