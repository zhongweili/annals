"""Local git archive: commit if dirty, optionally push. Push is not required
for the backup to be considered complete.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from annals.config import Config


class GitError(RuntimeError):
    pass


@dataclass
class GitResult:
    committed: bool
    files_changed: int
    pushed: bool
    push_error: str | None = None
    commit: str | None = None


def _git(repo: Path, *args: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    e = os.environ.copy()
    if env:
        e.update(env)
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=e,
    )
    if check and r.returncode != 0:
        raise GitError(r.stderr.strip() or r.stdout.strip() or f"git {args[0]} failed")
    return r


def global_git_email() -> str | None:
    r = subprocess.run(
        ["git", "config", "--global", "user.email"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def ensure_repo(cfg: Config) -> None:
    repo = cfg.archive.path
    repo.mkdir(parents=True, exist_ok=True)
    git_dir = repo / ".git"
    if not git_dir.exists():
        r = subprocess.run(
            ["git", "init", "-q", "-b", cfg.archive.branch, str(repo)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise GitError(r.stderr.strip() or "git init failed")
        _git(repo, "config", "pack.windowMemory", cfg.git.pack_window_memory)
        _git(repo, "config", "pack.packSizeLimit", cfg.git.pack_size_limit)
    if cfg.git.author_name:
        _git(repo, "config", "user.name", cfg.git.author_name)
    if cfg.git.author_email:
        _git(repo, "config", "user.email", cfg.git.author_email)
    # If neither is set, inherit whatever git would use. Refuse to commit
    # with no identity — that produces unusable history.
    ident = _git(repo, "config", "user.email", check=False)
    if ident.returncode != 0 or not ident.stdout.strip():
        if not cfg.git.author_email:
            raise GitError(
                "git user.email is unset; set [git].author_email in config "
                "or `git config --global user.email`"
            )


def commit_and_maybe_push(cfg: Config, log) -> GitResult:
    repo = cfg.archive.path
    ensure_repo(cfg)
    _git(repo, "add", "-A")
    dirty = _git(repo, "diff", "--cached", "--quiet", check=False)
    if dirty.returncode == 0:
        log("no changes, skipping commit")
        pushed = False
        push_err = None
        if cfg.archive.remote and cfg.archive.push:
            pushed, push_err = _push(cfg, log)
        return GitResult(False, 0, pushed, push_err)

    numstat = _git(repo, "diff", "--cached", "--numstat")
    n = len([ln for ln in numstat.stdout.splitlines() if ln.strip()])
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"annals backup [{cfg.archive.machine}] {stamp} — {n} files changed"
    _git(repo, "commit", "-q", "-m", msg)
    sha = _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    log(f"committed {sha}, {n} files changed")
    pushed = False
    push_err = None
    if cfg.archive.remote and cfg.archive.push:
        pushed, push_err = _push(cfg, log)
    return GitResult(True, n, pushed, push_err, sha)


def _push(cfg: Config, log) -> tuple[bool, str | None]:
    repo = cfg.archive.path
    name = cfg.archive.remote_name
    url = cfg.archive.remote
    assert url
    existing = _git(repo, "remote", "get-url", name, check=False)
    if existing.returncode != 0:
        _git(repo, "remote", "add", name, url)
    elif existing.stdout.strip() != url:
        _git(repo, "remote", "set-url", name, url)
    # ControlMaster reuse dies mid-push on large packs ("Broken pipe").
    env = {
        "GIT_SSH_COMMAND": (
            "ssh -o ControlMaster=no -o ControlPath=none "
            "-o ServerAliveInterval=20 -o ServerAliveCountMax=60 "
            "-o TCPKeepAlive=yes"
        )
    }
    r = _git(repo, "push", name, cfg.archive.branch, check=False, env=env)
    if r.returncode == 0:
        log(f"pushed {cfg.archive.branch} → {name}")
        return True, None
    err = (r.stderr or r.stdout).strip() or "git push failed"
    log(f"push failed (local archive intact): {err}")
    return False, err
