"""OpenCode adapter.

OpenCode stores conversations in a WAL-mode SQLite file. Putting that
binary in git costs a full copy every day the db changes (~29 MB/machine/day
measured). Instead: snapshot with the SQLite backup API, then emit one
JSON file per session. Only sessions whose canonical JSON changed are
rewritten, so git sees a real diff.

Nested snapshot/ git repos (OpenCode's own rollback store) are ignored.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from annals.adapters import Detected, HarvestResult
from annals.config import SourceConfig
from annals.sqliteutil import SqliteSnapshotError, snapshot_connection


class OpenCodeAdapter:
    kind = "opencode"

    def detect(self, src: SourceConfig) -> Detected:
        db = src.resolved_root()
        if db.is_file():
            return Detected(self.kind, db, True, True, str(db))
        return Detected(self.kind, db, False, True, "not found")

    def harvest(self, src: SourceConfig, dest: Path, log) -> HarvestResult:
        db = src.resolved_root()
        if not db.is_file():
            return HarvestResult(self.kind, True, f"skip (no {db})", 0, 0, 0)
        dest.mkdir(parents=True, exist_ok=True)
        try:
            written, unchanged = _export(db, dest)
        except SqliteSnapshotError as e:
            log(f"opencode snapshot failed: {e}")
            return HarvestResult(self.kind, False, str(e), 0, 0, 1)
        except Exception as e:  # schema drift should not abort the run
            log(f"opencode export failed: {e}")
            return HarvestResult(self.kind, False, str(e), 0, 0, 1)
        msg = (
            f"opencode ok wrote={written} unchanged={unchanged} → {dest}"
        )
        log(msg)
        return HarvestResult(self.kind, True, msg, written, unchanged, 0)


def _export(db: Path, out: Path) -> tuple[int, int]:
    written = unchanged = 0
    with snapshot_connection(db) as con:
        try:
            sessions = con.execute(
                "SELECT * FROM session ORDER BY time_created"
            ).fetchall()
        except Exception as e:
            raise RuntimeError(
                f"opencode schema unexpected (need table session): {e}"
            ) from e
        for s in sessions:
            row = dict(s)
            sid = row.get("id")
            if not sid:
                continue
            msgs = [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM message WHERE session_id=? ORDER BY time_created",
                    (sid,),
                )
            ]
            parts = [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM part WHERE session_id=? ORDER BY time_created",
                    (sid,),
                )
            ]
            ts = row.get("time_created") or 0
            try:
                month = dt.datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m")
            except (OSError, ValueError, OverflowError, TypeError):
                month = "unknown"
            d = out / month
            d.mkdir(parents=True, exist_ok=True)
            fpath = d / f"{sid}.json"
            body = json.dumps(
                {"session": _jsonable(row), "messages": _jsonable(msgs), "parts": _jsonable(parts)},
                ensure_ascii=False,
                indent=1,
                sort_keys=True,
            )
            if fpath.is_file() and fpath.read_text() == body:
                unchanged += 1
                continue
            fpath.write_text(body)
            written += 1
    return written, unchanged


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return obj


ADAPTER = OpenCodeAdapter()
