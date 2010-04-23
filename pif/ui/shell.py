import logging
import optparse
import os
import os.path
import re

import pif.index


LOG = logging.getLogger(__name__)


class Shell(object):
    EXTENSIONS = (
        'gif',
        'jpeg', 'jpg',
        'png',
    )
    RE_IMAGES = re.compile(r".*\.(%s)$" % '|'.join(EXTENSIONS), re.IGNORECASE)

    def __init__(self, args=None):
        self._init_option_parser()
        self.options, self.remain_args = self.option_parser.parse_args(
            args=args)

        self._init_logging()

    def _init_option_parser(self):
        self.option_parser = optparse.OptionParser(
            '%prog [options] <filename ...>')

        self.option_parser.add_option('-v', '--verbose', action='store_true',
                                       help='increase verbosity')

    def _init_logging(self):
        if 'DEBUG' in os.environ:
            logging.root.setLevel(logging.DEBUG)
        elif self.options.verbose:
            logging.root.setLevel(logging.INFO)
        else:
            logging.root.setLevel(logging.WARN)

    def make_index(self, *args, **kwargs):
        return pif.index.Index(*args, **kwargs)

    @property
    def filenames(self):
        for fn in self.remain_args:
            if os.path.isfile(fn):
                yield os.path.abspath(fn)
            elif os.path.isdir(fn):
                for root, dirs, files in os.walk(fn):
                    for fn in filter(self.RE_IMAGES.match, sorted(files)):
                        yield os.path.abspath(os.path.join(root, fn))
            else:
                LOG.warn("%s is not a file or a directory.", fn)
