from minimock import Mock, DefaultTracker

# TOOD: Implement a default dictionary tracker.

class MockDict(Mock):

    def __init__(self, name, returns=None, returns_iter=None,
                 returns_func=None, raises=None, show_attrs=False,
                 tracker=DefaultTracker, items=None, **kw):
        Mock.__init__(self, name, returns, returns_iter, returns_func, raises,
                      show_attrs, tracker, **kw)

        object.__setattr__(self, 'mock_items', items or {})

    def __setattr__(self, attr, value):
        if attr == 'mock_items':
            object.__setattr__(self, attr, value)
        return Mock.__setattr__(self, attr, value)

    def __len__(self):
        return len(self.mock_items)

    def __getitem__(self, key):
        if key not in self.mock_items:
            new_name = "%s[%s]" % (self.mock_name, key) \
                    if self.mock_name else key
            self.mock_items[key] = Mock(
                new_name,
                show_attrs=self.mock_show_attrs,
                tracker=self.mock_tracker)

        return self.mock_items[key]

    def __setitem__(self, key, value):
        self.mock_items[key] = value

    def __delitem__(self, key):
        del self.mock_items[key]

    def __iter__(self):
        return self.mock_items.__iter__()
