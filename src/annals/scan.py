"""Discover which agent CLIs are present on this machine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from annals.adapters import Detected, get
from annals.config import (
    DEFAULT_ROOTS,
    KNOWN_UNSUPPORTED,
    KINDS,
    Config,
    SourceConfig,
)


@dataclass
class ScanRow:
    kind: str
    supported: bool
    present: bool
    path: Path
    detail: str


def scan(cfg: Config | None = None) -> list[ScanRow]:
    rows: list[ScanRow] = []
    for kind in KINDS:
        src = (
            cfg.source(kind)
            if cfg is not None
            else SourceConfig(kind=kind, enabled=True)
        )
        if src is None:
            src = SourceConfig(kind=kind, enabled=True)
        det: Detected = get(kind).detect(src)
        rows.append(
            ScanRow(kind, det.supported, det.present, det.path, det.detail)
        )
    for kind, path in KNOWN_UNSUPPORTED.items():
        rows.append(
            ScanRow(
                kind,
                False,
                path.exists(),
                path,
                "present (no v1 adapter)" if path.exists() else "not found",
            )
        )
    return rows


def default_sources_from_disk() -> list[SourceConfig]:
    """Enable a source in `init` iff its default path exists."""
    out: list[SourceConfig] = []
    for kind, path in DEFAULT_ROOTS.items():
        out.append(SourceConfig(kind=kind, enabled=path.exists(), root=None))
    return out
