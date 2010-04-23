import logging
import time

from pif.ui.shell import Shell


LOG = logging.getLogger(__name__)


class ConsoleShell(Shell):
    """Console front-end."""

    def _init_option_parser(self):
        Shell._init_option_parser(self)

        self.option_parser.add_option('-f', '--force', action='store_true',
                                      help='force file(s) to be uploaded')
        self.option_parser.add_option('-m', '--mark', action='store_true',
                                      help='mark file(s) as uploaded')
        self.option_parser.add_option('-n', '--dry-run', action='store_true',
                                      help='do not upload file(s)')

    def proxy_callback(self, proxy, perms, token, frob):
        LOG.info('Waiting for authorization from Flickr...')
        LOG.debug('(If nothing happens, open %s in your browser.)',
                  proxy.auth_url(perms, frob))
        time.sleep(5)

    def progress_callback(self, state, meta):
        msgs = {
            'photos': 'Loading updates from Flickr...',
            'hashes': 'Indexing photos on Flickr...',
        }

        a, b = meta
        LOG.info("%s (%u / %u)", msgs[state], *meta)

    def run(self):
        try:
            index = self.make_index(self.proxy_callback,
                                    self.progress_callback)
        except IOError:
            return LOG.critical("Couldn't connect to Flickr.")

        for t, fn in ((index.type(fn), fn) for fn in self.filenames):
            if t == 'new' or (t == 'old' and self.options.force):
                if self.options.mark:
                    index.ignore(fn)

                    LOG.info("%s marked as already uploaded", fn)
                elif self.options.dry_run:
                    LOG.info("Would have uploaded %s", fn)
                else:

                    def _(progress, done):
                        if done:
                            LOG.info("Uploaded %s", fn)
                        else:
                            LOG.debug("Uploading %s... (%s%%)",
                                      fn, int(progress))

                    index.upload(fn, callback=_)
            elif t == 'old':
                LOG.info(
                    "%s already uploaded, skipping (use --force to upload)",
                    fn)
            elif t == 'invalid':
                LOG.warn("%s is invalid, skipping", fn)

        index.sync()


def run():
    s = ConsoleShell()
    s.run()
