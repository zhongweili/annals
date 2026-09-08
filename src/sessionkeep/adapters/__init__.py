from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sessionkeep.config import SourceConfig


@dataclass
class HarvestResult:
    kind: str
    ok: bool
    message: str
    copied: int = 0
    skipped: int = 0
    errors: int = 0


@dataclass
class Detected:
    kind: str
    path: Path
    present: bool
    supported: bool
    detail: str = ""


class Adapter(Protocol):
    kind: str

    def detect(self, src: SourceConfig) -> Detected: ...

    def harvest(self, src: SourceConfig, dest: Path, log) -> HarvestResult: ...


def get(kind: str) -> Adapter:
    from sessionkeep.adapters import claude, grok, opencode

    table = {
        claude.ADAPTER.kind: claude.ADAPTER,
        grok.ADAPTER.kind: grok.ADAPTER,
        opencode.ADAPTER.kind: opencode.ADAPTER,
    }
    try:
        return table[kind]
    except KeyError as e:
        raise KeyError(f"no adapter for {kind!r}") from e
