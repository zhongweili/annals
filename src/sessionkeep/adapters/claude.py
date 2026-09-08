"""Claude Code adapter.

Harvests project transcripts (jsonl) plus reconstructable memory
(CLAUDE.md, rules) and a sanitized settings.json. Skills, agents, hooks,
and any auth file stay out — those are environment, not conversation
history, and they are the highest-risk secret surface.
"""

from __future__ import annotations

from pathlib import Path

from sessionkeep.adapters import Detected, HarvestResult
from sessionkeep.config import SourceConfig
from sessionkeep.mirror import DEFAULT_EXCLUDE, copy_file, mirror_no_delete
from sessionkeep.sanitize import write_if_changed


class ClaudeAdapter:
    kind = "claude"

    def detect(self, src: SourceConfig) -> Detected:
        root = src.resolved_root()
        projects = root / "projects"
        if projects.is_dir():
            return Detected(self.kind, projects, True, True, str(projects))
        if root.exists():
            return Detected(
                self.kind, root, True, True, f"{root} (no projects/ yet)"
            )
        return Detected(self.kind, root, False, True, "not found")

    def harvest(self, src: SourceConfig, dest: Path, log) -> HarvestResult:
        root = src.resolved_root()
        if not root.exists():
            return HarvestResult(self.kind, True, f"skip (no {root})", 0, 0, 0)
        copied = skipped = errors = 0
        projects = root / "projects"
        if projects.is_dir():
            st = mirror_no_delete(projects, dest / "projects", exclude=DEFAULT_EXCLUDE)
            copied += st.copied
            skipped += st.skipped
            errors += st.errors
        md = root / "CLAUDE.md"
        if md.is_file() and copy_file(md, dest / "CLAUDE.md"):
            copied += 1
        else:
            skipped += 1
        rules = root / "rules"
        if rules.is_dir():
            st = mirror_no_delete(rules, dest / "rules", exclude=DEFAULT_EXCLUDE)
            copied += st.copied
            skipped += st.skipped
            errors += st.errors
        settings = root / "settings.json"
        if settings.is_file():
            wrote, hits = write_if_changed(settings, dest / "settings.sanitized.json")
            if wrote:
                copied += 1
                log(f"claude settings sanitized ({hits} redactions)")
            else:
                skipped += 1
        dest.mkdir(parents=True, exist_ok=True)
        msg = f"claude ok copied={copied} skipped={skipped} errors={errors}"
        log(msg)
        return HarvestResult(self.kind, errors == 0, msg, copied, skipped, errors)


ADAPTER = ClaudeAdapter()
