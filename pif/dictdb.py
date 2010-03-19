import json
import os
import os.path
import shutil
import tempfile

import eventlet.tpool


class DictDB(dict):
    def __init__(self, filename):
        self.filename = filename

        if os.access(filename, os.R_OK):
            with open(filename) as f:
                self.update(eventlet.tpool.execute(json.load, f))

    def sync(self):
        f = tempfile.NamedTemporaryFile(
            suffix=os.path.basename(self.filename),
            dir=os.path.dirname(self.filename),
            delete=False)

        try:
            with f:
                eventlet.tpool.execute(json.dump, self, f)
        except:
            os.remove(f.name)
            raise

        shutil.move(f.name, self.filename)    # atomic commit
