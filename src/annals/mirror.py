"""Copy source → dest without ever deleting dest files.

This is the core invariant. Agent CLIs treat transcripts as cache and
silently prune them. rsync --delete (or a 'sync' tool) would throw the
archive away with the cache. We only add and update.
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

ExcludeFn = Callable[[Path, str], bool]


@dataclass
class MirrorStats:
    copied: int = 0
    skipped: int = 0
    errors: int = 0
    error_paths: list[str] = field(default_factory=list)


def exclude_names(*names: str) -> ExcludeFn:
    nset = set(names)

    def fn(_rel: Path, name: str) -> bool:
        return name in nset

    return fn


def exclude_prefixes(*prefixes: str) -> ExcludeFn:
    def fn(_rel: Path, name: str) -> bool:
        return any(name.startswith(p) for p in prefixes)

    return fn


def exclude_suffixes(*suffixes: str) -> ExcludeFn:
    def fn(_rel: Path, name: str) -> bool:
        return any(name.endswith(s) for s in suffixes)

    return fn


def any_exclude(*fns: ExcludeFn) -> ExcludeFn:
    def fn(rel: Path, name: str) -> bool:
        return any(f(rel, name) for f in fns)

    return fn


DEFAULT_EXCLUDE = any_exclude(
    exclude_names(".DS_Store"),
    exclude_suffixes(".lock"),
)


def mirror_no_delete(
    src: Path,
    dst: Path,
    *,
    exclude: ExcludeFn = DEFAULT_EXCLUDE,
) -> MirrorStats:
    """Recursively copy *src* into *dst*. Never remove anything under *dst*."""
    stats = MirrorStats()
    if not src.exists():
        return stats
    dst.mkdir(parents=True, exist_ok=True)

    if src.is_file() or src.is_symlink():
        _copy_one(src, dst if dst.is_dir() and src.is_file() else dst, src.name, stats)
        return stats

    for root, dirs, files in os.walk(src, followlinks=False):
        root_p = Path(root)
        rel_root = root_p.relative_to(src)
        # Prune excluded directories in-place so we don't descend.
        keep: list[str] = []
        for d in dirs:
            rel = rel_root / d if rel_root.parts else Path(d)
            if exclude(rel, d):
                continue
            keep.append(d)
        dirs[:] = keep
        dest_dir = dst / rel_root if rel_root.parts else dst
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            rel = rel_root / name if rel_root.parts else Path(name)
            if exclude(rel, name):
                stats.skipped += 1
                continue
            _copy_one(root_p / name, dest_dir / name, name, stats)
        # Directory-level symlinks show up in dirs; os.walk doesn't follow
        # them (followlinks=False) but also doesn't copy them. Copy as links.
        for d in os.listdir(root_p):
            p = root_p / d
            if p.is_symlink() and p.is_dir():
                rel = rel_root / d if rel_root.parts else Path(d)
                if exclude(rel, d):
                    continue
                _copy_one(p, dest_dir / d, d, stats)
    return stats


def _copy_one(src: Path, dst: Path, name: str, stats: MirrorStats) -> None:
    try:
        if src.is_symlink():
            target = os.readlink(src)
            if dst.is_symlink() or dst.exists():
                if dst.is_symlink() and os.readlink(dst) == target:
                    stats.skipped += 1
                    return
                if dst.is_dir() and not dst.is_symlink():
                    # Refuse to replace a real directory with a symlink.
                    stats.errors += 1
                    stats.error_paths.append(str(src))
                    return
                dst.unlink()
            dst.symlink_to(target)
            stats.copied += 1
            return
        if not src.is_file():
            stats.skipped += 1
            return
        if _same_file(src, dst):
            stats.skipped += 1
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst, follow_symlinks=False)
        stats.copied += 1
    except OSError:
        stats.errors += 1
        stats.error_paths.append(str(src))


def _same_file(src: Path, dst: Path) -> bool:
    if not dst.exists() or dst.is_symlink():
        return False
    try:
        ss, ds = src.stat(), dst.stat()
    except OSError:
        return False
    if not stat.S_ISREG(ss.st_mode) or not stat.S_ISREG(ds.st_mode):
        return False
    return ss.st_size == ds.st_size and int(ss.st_mtime) == int(ds.st_mtime)


def copy_file(src: Path, dst: Path) -> bool:
    """Copy a single file if contents-or-mtime differ. Returns True if wrote."""
    if not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if _same_file(src, dst):
        return False
    shutil.copy2(src, dst)
    return True


def iter_error_sample(paths: Iterable[str], n: int = 5) -> list[str]:
    out = list(paths)
    return out[:n]
