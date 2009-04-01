import logging

from pif.ui import OPTIONS, common_run

LOG = logging.getLogger(__name__)

def proxy_callback():
    LOG.info('Waiting for authorization from Flickr...')
    time.sleep(5)

def progress_callback(state, meta):
    a, b = meta
    LOG.debug("Flickr: %s, %u / %u" % (state, a, b))

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
                flickr_index.add(file_index[fn], None)

            LOG.info("\t%s" % fn)
    else:
        for fn in images:
            def _(progress, done):
                if done:
                    LOG.info("Uploaded %s" % fn)
                else:
                    LOG.debug("Uploading %s... (%s%%)" % progress)

            if options.dry_run:
                LOG.info("Uploaded %s" % fn)
            else:
                flickr_index.upload(filename=fn, callback=_)

    file_index.sync()

    if not options.dry_run:
        flickr_index.sync()
