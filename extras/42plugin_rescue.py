#!/usr/bin/env python3
"""contrib: rescue Claude sessions that exist only in 42plugin's plugin.db.

This is NOT a v1 adapter. It binds to 42plugin's internal SQLite schema,
which is not a public contract. Kept as a contrib script because it has
recovered hundreds of conversations after Claude Code pruned jsonl files.

`--projects` must point at the *archive* copy of ~/.claude/projects, not
the live directory. The archive is a superset (no-delete), so "not in the
archive" is the real missing set.

Usage:
  python extras/42plugin_rescue.py \
    --db ~/.42plugin/plugin.db \
    --projects ~/sessionkeep-archive/MACHINE/claude/projects \
    --out ~/sessionkeep-archive/MACHINE/42plugin-rescued
"""
from __future__ import annotations

import argparse
import glob
import os
import sqlite3
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--projects", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    a = ap.parse_args()

    db = os.path.expanduser(a.db)
    proj = os.path.expanduser(a.projects)
    out = os.path.expanduser(a.out)
    if not os.path.exists(db):
        print(f"skip: db not found {db}")
        return 0

    ondisk = {
        os.path.basename(p)[:-6]
        for p in glob.glob(os.path.join(proj, "**", "*.jsonl"), recursive=True)
    }

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        sessions = con.execute(
            "SELECT session_id, started_at, last_message_at, message_count, "
            "project_name, preview FROM conversation_sessions ORDER BY started_at"
        ).fetchall()
    except sqlite3.Error as e:
        print(f"42plugin schema unexpected: {e}", file=sys.stderr)
        return 1

    rescued = skipped = 0
    for s in sessions:
        sid = s["session_id"]
        if sid in ondisk:
            continue
        month = (s["started_at"] or "0000-00")[:7]
        day = (s["started_at"] or "0000-00-00")[:10]
        d = os.path.join(out, month)
        os.makedirs(d, exist_ok=True)
        fpath = os.path.join(d, f"{day}-{sid[:8]}.md")
        if os.path.exists(fpath):
            skipped += 1
            continue
        msgs = con.execute(
            "SELECT role, content, timestamp FROM conversation_messages "
            "WHERE session_id=? ORDER BY id",
            (sid,),
        ).fetchall()
        origin = f" [{a.label}]" if a.label else ""
        lines = [
            f"# {s['project_name'] or 'session'} — {day}",
            "",
            f"- session_id: `{sid}`",
            f"- started_at: {s['started_at']}",
            f"- last_message_at: {s['last_message_at']}",
            f"- message_count: {s['message_count']}",
            f"- source: 42plugin plugin.db{origin} (rescued — deleted from disk)",
            "",
            "---",
            "",
        ]
        for m in msgs:
            lines += [f"## {m['role']}  ·  {m['timestamp']}", "", m["content"] or "", ""]
        with open(fpath, "w") as fh:
            fh.write("\n".join(lines))
        rescued += 1
    tag = f"[{a.label}] " if a.label else ""
    print(f"{tag}rescued {rescued}, skipped {skipped} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
