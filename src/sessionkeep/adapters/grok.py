"""Grok / xAI CLI adapter.

Sessions are files and can be mirrored. Memory markdown is small and
worth keeping. The FTS5 + vector index (index.sqlite*) is rebuildable
and was measured at ~99% of ~/.grok/memory by size — do not archive it.
auth.json is 600 and holds real credentials — do not archive it.
config.toml is copied as-is: env_key values are variable *names*, not secrets.
"""

from __future__ import annotations

from pathlib import Path

from sessionkeep.adapters import Detected, HarvestResult
from sessionkeep.config import SourceConfig
from sessionkeep.mirror import (
    DEFAULT_EXCLUDE,
    any_exclude,
    copy_file,
    exclude_names,
    exclude_prefixes,
    mirror_no_delete,
)
from sessionkeep.sanitize import write_if_changed

MEMORY_EXCLUDE = any_exclude(
    DEFAULT_EXCLUDE,
    exclude_prefixes("index.sqlite"),
    exclude_names(".dream-lock"),
)


class GrokAdapter:
    kind = "grok"

    def detect(self, src: SourceConfig) -> Detected:
        root = src.resolved_root()
        sessions = root / "sessions"
        if sessions.is_dir():
            return Detected(self.kind, sessions, True, True, str(sessions))
        if root.exists():
            return Detected(self.kind, root, True, True, str(root))
        return Detected(self.kind, root, False, True, "not found")

    def harvest(self, src: SourceConfig, dest: Path, log) -> HarvestResult:
        root = src.resolved_root()
        if not root.exists():
            return HarvestResult(self.kind, True, f"skip (no {root})", 0, 0, 0)
        copied = skipped = errors = 0
        sessions = root / "sessions"
        if sessions.is_dir():
            st = mirror_no_delete(sessions, dest / "sessions", exclude=DEFAULT_EXCLUDE)
            copied += st.copied
            skipped += st.skipped
            errors += st.errors
        memory = root / "memory"
        if memory.is_dir():
            st = mirror_no_delete(memory, dest / "memory", exclude=MEMORY_EXCLUDE)
            copied += st.copied
            skipped += st.skipped
            errors += st.errors
        cfg = root / "config.toml"
        if cfg.is_file() and copy_file(cfg, dest / "config.toml"):
            copied += 1
        settings = root / "settings.json"
        if settings.is_file():
            wrote, hits = write_if_changed(settings, dest / "settings.sanitized.json")
            copied += int(wrote)
            skipped += int(not wrote)
            if wrote:
                log(f"grok settings sanitized ({hits} redactions)")
        # Explicitly never copy these even if a future layout change
        # puts them next to sessions.
        for banned in ("auth.json", "auth.json.lock"):
            p = dest / banned
            if p.exists():
                p.unlink()
                log(f"removed {banned} from archive (credentials)")
        msg = f"grok ok copied={copied} skipped={skipped} errors={errors}"
        log(msg)
        return HarvestResult(self.kind, errors == 0, msg, copied, skipped, errors)


ADAPTER = GrokAdapter()
