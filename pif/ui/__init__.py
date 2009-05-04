__all__ = [
    'console',
    'x',
]

import logging
import optparse
import os
import os.path
import re

import pif.flickr
import pif.local

LOG = logging.getLogger(__name__)

if 'DEBUG' in os.environ:
    logging.root.setLevel(logging.DEBUG)

EXTENSIONS = ('gif',
              'jpeg', 'jpg',
              'png',)

RE_IMAGES = re.compile(r".*\.(%s)$" % '|'.join(EXTENSIONS),
                       re.IGNORECASE)

CONFIG_DIR = os.path.expanduser('~/.pif')
FILE_INDEX = os.path.join(CONFIG_DIR, 'file.db')
FLICKR_INDEX = os.path.join(CONFIG_DIR, 'flickr.db')

OPTIONS = optparse.OptionParser('%prog [options] <filename filename...>')
OPTIONS.add_option('-f', '--force', action='store_true',
                   help='force file(s) to be uploaded')
OPTIONS.add_option('-n', '--dry-run', action='store_true',
                   help='perform a trial run with no uploads made')
OPTIONS.add_option('-r', '--reset', action='store_true',
                   help='reset the local Flickr index')
OPTIONS.add_option('-x', '--no-refresh', action='store_true',
                   help='do not refresh the local Flickr index')
OPTIONS.add_option('-v', '--verbose', action='store_true',
                   help='increase verbosity')

def open_proxy(callback):
    try:
        return pif.flickr.get_proxy(wait_callback=callback)
    except (pif.flickr.FlickrError, IOError):
        LOG.error('Could not connect to Flickr.')
        return None

def open_indexes(proxy):
    # Make sure we can land the indexes.
    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    return pif.local.FileIndex(FILE_INDEX), pif.flickr.FlickrIndex(proxy, FLICKR_INDEX)

def normalized_filelist(filenames):
    for fn in filenames:
        if os.path.isfile(fn):
            yield os.path.abspath(fn)
        elif os.path.isdir(fn):
            for root, dirs, files in os.walk(fn):
                for fn in filter(RE_IMAGES.match, sorted(files)):
                    yield os.path.abspath(os.path.join(root, fn))
        else:
            LOG.warn("%s is not a file or a directory." % fn)

def images_not_uploaded(indexes, filenames):
    file_index, flickr_index = indexes

    for fn in filenames:
        try:
            if file_index[fn] in flickr_index:
                LOG.info("%s skipped. (--force to upload)" % fn)
            else:
                yield fn
        except KeyError:    # Skip invalid files.
            LOG.warn("%s is invalid and was skipped." % fn)

def common_run(opts, proxy_callback, progress_callback):
    options, args = opts

    if 'DEBUG' not in os.environ:
        if options.verbose:
            logging.root.setLevel(logging.INFO)
        else:
            logging.root.setLevel(logging.WARN)

    # (Maybe) Reset the Flickr index.

    if options.reset and os.path.isfile(FLICKR_INDEX):
        os.remove(FLICKR_INDEX)

    # Get the Flickr proxy and open the indexes.

    proxy = open_proxy(proxy_callback)

    file_index, flickr_index = open_indexes(proxy)

    # (Maybe) Refresh the Flickr index.

    if not options.no_refresh:
        try:
            flickr_index.refresh(progress_callback)
        except (pif.flickr.FlickrError, IOError):
            flickr_index = None

            LOG.exception('Flickr refresh failed.')

    # Find images to be uploaded.

    images = normalized_filelist(args)

    if not options.force:
        images = images_not_uploaded((file_index, flickr_index), images)

    return (file_index, flickr_index), images
