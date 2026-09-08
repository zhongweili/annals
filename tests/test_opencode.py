import json
import sqlite3
from pathlib import Path

from sessionkeep.adapters.opencode import _export
from sessionkeep.config import SourceConfig
from sessionkeep.sqliteutil import snapshot_connection


def _make_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    con.executescript(
        """
        CREATE TABLE session (
            id TEXT PRIMARY KEY,
            time_created INTEGER
        );
        CREATE TABLE message (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            time_created INTEGER,
            role TEXT,
            content TEXT
        );
        CREATE TABLE part (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            time_created INTEGER,
            type TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO session VALUES (?, ?)", ("ses_aaa", 1_700_000_000_000)
    )
    con.execute(
        "INSERT INTO message (session_id, time_created, role, content) VALUES (?,?,?,?)",
        ("ses_aaa", 1_700_000_000_000, "user", "hello"),
    )
    con.commit()
    con.close()


def test_export_splits_sessions(tmp_path: Path):
    db = tmp_path / "opencode.db"
    _make_db(db)
    out = tmp_path / "out"
    written, unchanged = _export(db, out)
    assert written == 1 and unchanged == 0
    files = list(out.glob("**/*.json"))
    assert len(files) == 1
    body = json.loads(files[0].read_text())
    assert body["session"]["id"] == "ses_aaa"
    assert body["messages"][0]["content"] == "hello"


def test_export_is_idempotent(tmp_path: Path):
    db = tmp_path / "opencode.db"
    _make_db(db)
    out = tmp_path / "out"
    _export(db, out)
    written, unchanged = _export(db, out)
    assert written == 0 and unchanged == 1


def test_snapshot_survives_wal(tmp_path: Path):
    db = tmp_path / "opencode.db"
    _make_db(db)
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        "INSERT INTO session VALUES (?, ?)", ("ses_bbb", 1_700_000_000_100)
    )
    con.commit()
    # Leave WAL uncheckpointed.
    with snapshot_connection(db) as snap:
        ids = [r[0] for r in snap.execute("SELECT id FROM session")]
    con.close()
    assert "ses_aaa" in ids and "ses_bbb" in ids


def test_detect_missing(tmp_path: Path):
    from sessionkeep.adapters.opencode import ADAPTER

    d = ADAPTER.detect(SourceConfig(kind="opencode", root=tmp_path / "nope.db"))
    assert d.present is False
