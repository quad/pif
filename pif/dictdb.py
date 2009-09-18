'''Alternate DB based on a dict subclass

Runs like gdbm's fast mode (all writes all delayed until close).
While open, the whole dict is kept in memory.  Start-up and
close time's are potentially long because the whole dict must be
read or written to disk.

Input file format is automatically discovered.
Output file format is selectable between pickle, json, and csv.
All three are backed by fast C implementations.

'''

import pickle, json, csv
import os, shutil

class DictDB(dict):

    def __init__(self, filename, flag=None, mode=None, format=None, *args, **kwds):
        self.flag = flag or 'c'             # r=readonly, c=create, or n=new
        self.mode = mode                    # None or octal triple like 0x666
        self.format = format or 'csv'       # csv, json, or pickle
        self.filename = filename
        if flag != 'n' and os.access(filename, os.R_OK):
            file = __builtins__.open(filename, 'rb')
            try:
                self.load(file)
            finally:
                file.close()
        self.update(*args, **kwds)

    def sync(self):
        if self.flag == 'r':
            return
        filename = self.filename
        tempname = filename + '.tmp'
        file = __builtins__.open(tempname, 'wb')
        try:
            self.dump(file)
        except Exception:
            file.close()
            os.remove(tempname)
            raise
        file.close()
        shutil.move(tempname, self.filename)    # atomic commit
        if self.mode is not None:
            os.chmod(self.filename, self.mode)

    def close(self):
        self.sync()

    def dump(self, file):
        if self.format == 'csv':
            csv.writer(file).writerows(self.iteritems())
        elif self.format == 'json':
            json.dump(self, file, separators=(',', ':'))
        elif self.format == 'pickle':
            pickle.dump(self.items(), file, -1)
        else:
            raise NotImplementedError('Unknown format: %r' % self.format)

    def load(self, file):
        # try formats from most restrictive to least restrictive
        for loader in (pickle.load, json.load, csv.reader):
            file.seek(0)
            try:
                return self.update(loader(file))
            except Exception:
                pass
        raise ValueError('File not in recognized format')


def dbopen(filename, flag=None, mode=None, format=None):
    return DictDB(filename, flag, mode, format)



if __name__ == '__main__':
    import random
    os.chdir('/dbm_sqlite/alt')
    print(os.getcwd())
    s = dbopen('tmp.shl', 'c', format='json')
    print(s, 'start')
    s['abc'] = '123'
    s['rand'] = random.randrange(10000)
    s.close()
    f = __builtins__.open('tmp.shl', 'rb')
    print (f.read())
    f.close()
