"""Consistent snapshots of live SQLite databases (WAL-safe).

`file:path?mode=ro` is fragile: some SQLite builds want `file:///abs`,
and a live WAL can make `mode=ro` fail with 'unable to open database
file'. We try several strategies and always go through the backup API
so the snapshot includes uncheckpointed WAL frames.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class SqliteSnapshotError(RuntimeError):
    pass


@contextmanager
def snapshot_connection(db: Path, timeout: float = 30.0) -> Iterator[sqlite3.Connection]:
    """Yield a read-only connection to a consistent snapshot of *db*."""
    if not db.is_file():
        raise SqliteSnapshotError(f"database not found: {db}")
    tmp = Path(tempfile.mkdtemp(prefix="annals-sqlite-"))
    snap = tmp / "snap.db"
    last_err: Exception | None = None
    try:
        for opener in (_open_path, _open_uri_ro, lambda p: _open_copied(p, tmp)):
            src: sqlite3.Connection | None = None
            try:
                src = opener(db)
                dst = sqlite3.connect(str(snap))
                try:
                    with dst:
                        src.backup(dst)
                finally:
                    dst.close()
                if src is not None:
                    src.close()
                    src = None
                con = sqlite3.connect(f"file:{snap}?mode=ro", uri=True)
                con.row_factory = sqlite3.Row
                try:
                    yield con
                finally:
                    con.close()
                return
            except sqlite3.Error as e:
                last_err = e
                if src is not None:
                    try:
                        src.close()
                    except sqlite3.Error:
                        pass
                continue
        raise SqliteSnapshotError(
            f"could not snapshot {db}: {last_err}"
        ) from last_err
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _open_path(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _open_uri_ro(db: Path) -> sqlite3.Connection:
    uri = db.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.execute("PRAGMA query_only=ON")
    return con


def _open_copied(db: Path, tmp: Path) -> sqlite3.Connection:
    """Last resort: copy db + WAL + SHM, then open the copy.

    This can theoretically tear if a writer checkpoints mid-copy. It is
    strictly better than failing the harvest, and the next run will
    rewrite any torn session file whose content later stabilizes.
    """
    copy = tmp / "live-copy.db"
    shutil.copy2(db, copy)
    for suffix in ("-wal", "-shm"):
        side = Path(str(db) + suffix)
        if side.exists():
            shutil.copy2(side, Path(str(copy) + suffix))
    return sqlite3.connect(str(copy), timeout=30)
