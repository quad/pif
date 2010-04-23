import json
import os
import os.path
import shutil
import tempfile


class DictDB(dict):
    """A persistant JSON dictionary."""

    def __init__(self, filename):
        self.filename = filename

        if os.access(filename, os.R_OK):
            with open(filename) as f:
                self.update(json.load(f))

    def sync(self):
        f = tempfile.NamedTemporaryFile(
            suffix=os.path.basename(self.filename),
            dir=os.path.dirname(self.filename),
            delete=False)

        try:
            with f:
                json.dump(self, f)
        except:
            os.remove(f.name)
            raise

        shutil.move(f.name, self.filename)    # atomic commit
