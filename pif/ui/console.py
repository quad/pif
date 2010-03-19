import logging
import time

from pif.ui.shell import Shell

LOG = logging.getLogger(__name__)


class ConsoleShell(Shell):
    def _init_option_parser(self):
        Shell._init_option_parser(self)

        self.option_parser.add_option('-f', '--force', action='store_true',
                                      help='force file(s) to be used')
        self.option_parser.add_option('-m', '--mark', action='store_true',
                                      help='mark files as uploaded')

    def proxy_callback(self, proxy, perms, token, frob):
        LOG.info('Waiting for authorization from Flickr...')
        LOG.info('(If nothing happens, open %s in your browser.)',
                 proxy.auth_url(perms, frob))
        time.sleep(5)

    def progress_callback(self, state, meta):
        msgs = {
            'photos': 'Loading updates from Flickr...',
            'hashes': 'Indexing photos on Flickr...',
        }

        a, b = meta
        LOG.info("%s (%u / %u)" % (msgs[state], a, b))

    def run(self):
        try:
            index = self.make_index(self.proxy_callback,
                                    self.progress_callback)
        except IOError:
            return LOG.fatal("Couldn't connect to Flickr.")

        for t, fn in ((index.type(fn), fn) for fn in self.filenames):
            if t == 'new' or (t == 'old' and self.options.force):
                if self.options.mark:
                    index.ignore(fn)

                    LOG.info("%s marked as already uploaded" % fn)
                else:

                    def _(progress, done):
                        if done:
                            print
                            LOG.info("Uploaded %s" % fn)
                        else:
                            print "\rUploading %s... (%s%%)" % (
                                fn, int(progress)),

                    index.upload(fn, callback=_)
            elif t == 'old':
                LOG.info(
                    "%s already uploaded, skipping (use --force to upload)",
                    fn)
            elif t == 'invalid':
                LOG.warn("%s is invalid, skipping" % fn)
            else:
                LOG.debug("%s is type '%s'?" % (fn, t))

        index.sync()


def run():
    s = ConsoleShell()
    s.run()
