import json
import os
import tempfile

import minimock

from minimock import assert_same_trace
from nose.tools import raises

from pif.dictdb import DictDB


class TestInits:
    """Tests for the initialization of the DictDB."""

    def setUp(self):
        self.file = tempfile.NamedTemporaryFile()

        self.trace = minimock.TraceTracker()
        minimock.mock('json.load', tracker=self.trace)

    def tearDown(self):
        minimock.restore()

        self.file.close()

    @raises(TypeError)
    def test_init_bad_file(self):
        """DictDB chokes reading an invalid file"""

        DictDB(self.file.name)

    def test_init_exists(self):
        """DictDB inits reading a previously existing file"""

        json.load.mock_returns = {}

        assert DictDB(self.file.name) == {}
        assert_same_trace(self.trace, "Called json.load(<open file '%s', mode 'r' at 0x...>)" % self.file.name)
