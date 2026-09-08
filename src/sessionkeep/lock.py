"""Exclusive lock on the archive so overlapping launchd/cron runs skip."""

from __future__ import annotations

import sys
from pathlib import Path
from types import TracebackType

if sys.platform == "win32":  # pragma: no cover - v1 is Unix
    raise RuntimeError("sessionkeep v1 does not support Windows")

import fcntl


class ArchiveLock:
    def __init__(self, archive: Path):
        self.path = archive / ".sessionkeep.lock"
        self._fh = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._fh.close()
            self._fh = None
            return False
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(str(os_getpid()) + "\n")
        self._fh.flush()
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def os_getpid() -> int:
    import os

    return os.getpid()
