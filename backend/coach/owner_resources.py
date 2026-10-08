"""Process-local integration locks and cancellation events, isolated by owner and volume."""

import threading

from coach.config import root_data_dir, user_id


class OwnerResource:
    def __init__(self, factory):
        self.factory = factory
        self.values = {}
        self.guard = threading.Lock()

    def current(self):
        key = (str(root_data_dir()), user_id())
        with self.guard:
            if key not in self.values:
                self.values[key] = self.factory()
            return self.values[key]

    def __getattr__(self, name):
        return getattr(self.current(), name)


class OwnerLock(OwnerResource):
    def __init__(self):
        super().__init__(threading.Lock)


class OwnerEvent(OwnerResource):
    def __init__(self):
        super().__init__(threading.Event)

    def set(self):
        return self.current().set()

    def clear(self):
        return self.current().clear()

    def is_set(self):
        return self.current().is_set()

    def wait(self, timeout=None):
        return self.current().wait(timeout)
