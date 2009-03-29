import logging

from pif.ui import OPTIONS, common_run, upload_images

LOG = logging.getLogger(__name__)

def proxy_callback():
    LOG.info('Waiting for authorization from Flickr...')
    time.sleep(5)

def run():
    OPTIONS.add_option('-m', '--mark', action='store_true',
                       help='mark files as uploaded')
    options, args = OPTIONS.parse_args()

    indexes, images = common_run((options, args), proxy_callback)
    file_index, flickr_index = indexes

    if options.mark:
        LOG.info('Marked as uploaded:')
        for fn in images:
            if not options.dry_run:
                flickr_index.add(file_index[fn], None)

            LOG.info("\t%s" % fn)
    else:
        upload_images(images)

    file_index.sync()
    flickr_index.sync()
