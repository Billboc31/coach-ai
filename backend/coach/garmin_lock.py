"""Serialize provider-token rotation across the API worker and CLI processes."""

import os
from contextlib import contextmanager

from coach.config import data_dir


@contextmanager
def storage_lock(name="garmin"):
    path = data_dir() / f"{name}.lock"
    with path.open("a+b") as handle:
        try:
            if os.name == "posix":
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt

                handle.write(b"0")
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise ValueError(f"Une autre opération {name} utilise déjà la session.") from None
        try:
            yield
        finally:
            if os.name == "posix":
                fcntl.flock(handle, fcntl.LOCK_UN)
            else:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
