"""annals CLI: init / scan / backup / status."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from annals import __version__
from annals.adapters import get
from annals.config import (
    DEFAULT_CONFIG_PATH,
    ArchiveConfig,
    Config,
    ConfigError,
    GitConfig,
    default_machine,
    dumps,
    load,
    write as write_config,
)
from annals.gitstore import (
    GitError,
    commit_and_maybe_push,
    ensure_repo,
    global_git_email,
)
from annals.lock import ArchiveLock
from annals.scan import default_sources_from_disk, scan as scan_machine


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "fn"):
        parser.print_help()
        return 2
    try:
        return args.fn(args)
    except ConfigError as e:
        print(f"annals: {e}", file=sys.stderr)
        return 2
    except GitError as e:
        print(f"annals: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def _add_config_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="config TOML (default: $ANNALS_CONFIG or ~/.config/annals/config.toml)",
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="annals",
        description=(
            "Append-only git archive for coding-agent sessions. "
            "Agent CLIs treat chat history as cache; annals treats it as an archive."
        ),
    )
    p.add_argument("--version", action="version", version=f"annals {__version__}")
    _add_config_flag(p)
    sub = p.add_subparsers(dest="cmd")

    init = sub.add_parser("init", help="write a config after scanning this machine")
    _add_config_flag(init)
    init.add_argument("--machine", default=None, help="machine id (default: hostname)")
    init.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="archive git repo path (default: ~/annals-archive)",
    )
    init.add_argument("--branch", default=None, help="git branch (default: machine id)")
    init.add_argument("--remote", default=None, help="optional git remote URL")
    init.add_argument(
        "--force", action="store_true", help="overwrite an existing config"
    )
    init.set_defaults(fn=cmd_init)

    sc = sub.add_parser("scan", help="show which agent CLIs are present")
    _add_config_flag(sc)
    sc.set_defaults(fn=cmd_scan)

    bk = sub.add_parser("backup", help="harvest sessions into the archive")
    _add_config_flag(bk)
    bk.add_argument("--dry-run", action="store_true", help="scan only, write nothing")
    bk.add_argument("--no-push", action="store_true", help="commit locally, do not push")
    bk.set_defaults(fn=cmd_backup)

    st = sub.add_parser("status", help="archive size, last commit, remote")
    _add_config_flag(st)
    st.set_defaults(fn=cmd_status)
    return p


def _cfg(args) -> Config:
    return load(args.config)


def cmd_init(args) -> int:
    dest = args.config or DEFAULT_CONFIG_PATH
    if dest.exists() and not args.force:
        print(f"config already exists: {dest} (pass --force to overwrite)")
        return 2
    machine = args.machine or default_machine()
    archive = args.archive or (Path.home() / "annals-archive")
    branch = args.branch or machine
    cfg = Config(
        archive=ArchiveConfig(
            path=archive.expanduser(),
            machine=machine,
            branch=branch,
            remote=args.remote,
            push=bool(args.remote),
        ),
        git=GitConfig(),
        sources=default_sources_from_disk(),
    )
    write_config(cfg, dest)
    print(f"wrote {dest}")
    print()
    print(dumps(cfg), end="")
    print()
    if global_git_email() is None:
        print(
            "next step: this machine has no `git config --global user.email`, so "
            "backup cannot commit.\n"
            f"  set one:  git config --global user.email you@example.com\n"
            f"  or edit:  {dest}  → uncomment [git].author_email"
        )
    if not any(s.enabled for s in cfg.sources):
        print("note: no known agent paths were found; sources are all enabled=false")
    return 0


def cmd_scan(args) -> int:
    cfg = None
    try:
        cfg = load(args.config)
    except ConfigError:
        pass
    rows = scan_machine(cfg)
    width = max(len(r.kind) for r in rows)
    for r in rows:
        flag = "ok" if r.supported and r.present else (
            "unsupported" if r.present and not r.supported else "—"
        )
        print(f"{r.kind:<{width}}  {flag:<12}  {r.detail or r.path}")
    return 0


def cmd_backup(args) -> int:
    cfg = _cfg(args)
    if args.no_push:
        cfg.archive.push = False
    if args.dry_run:
        for row in scan_machine(cfg):
            print(f"{row.kind}: {row.detail or row.path}")
        return 0

    state_dir = cfg.archive.resolved_state_dir()
    log = _logger(state_dir)
    lock = ArchiveLock(state_dir)
    if not lock.acquire():
        log("backup already running, skip")
        return 0
    try:
        return _backup(cfg, log)
    finally:
        lock.release()


def _backup(cfg: Config, log) -> int:
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    log(f"===== {stamp} backup start machine={cfg.archive.machine} =====")
    # Fail before harvesting: a missing git identity would otherwise let the
    # harvest write the whole archive and only then refuse to commit it.
    try:
        ensure_repo(cfg)
    except GitError as e:
        log(f"git failed: {e}")
        return 1
    dest_root = cfg.archive.path / cfg.archive.machine
    dest_root.mkdir(parents=True, exist_ok=True)
    results = []
    for src in cfg.enabled_sources():
        adapter = get(src.kind)
        dest = dest_root / src.kind
        try:
            results.append(adapter.harvest(src, dest, log))
        except Exception as e:
            log(f"{src.kind} failed: {e}")
            from annals.adapters import HarvestResult

            results.append(HarvestResult(src.kind, False, str(e), errors=1))
    if cfg.enabled_sources() and all(not r.ok for r in results):
        log("all sources failed")
        return 1
    try:
        git = commit_and_maybe_push(cfg, log)
    except GitError as e:
        log(f"git failed: {e}")
        return 1
    size = _du(cfg.archive.path)
    log(f"archive size {size}")
    log("===== done =====")
    if git.push_error:
        # Local archive is the backup. Push is extra. Non-zero would make
        # launchd look like the run failed when it didn't.
        return 0
    return 0


def cmd_status(args) -> int:
    cfg = _cfg(args)
    repo = cfg.archive.path
    print(f"config:   {cfg.path}")
    print(f"archive:  {repo}")
    print(f"machine:  {cfg.archive.machine}")
    print(f"branch:   {cfg.archive.branch}")
    print(f"remote:   {cfg.archive.remote or '(none)'}")
    print(f"state:    {cfg.archive.resolved_state_dir()}")
    if not (repo / ".git").exists():
        print("git:      not initialized (run backup)")
        return 0
    import subprocess

    def g(*a):
        return subprocess.run(
            ["git", "-C", str(repo), *a], capture_output=True, text=True
        )

    head = g("log", "-1", "--format=%h %ci %s")
    if head.returncode == 0 and head.stdout.strip():
        print(f"head:     {head.stdout.strip()}")
    else:
        print("head:     no commits")
    print(f"size:     {_du(repo)}")
    return 0


def _logger(state_dir: Path):
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "annals.log"

    def log(msg: str) -> None:
        line = msg if msg.endswith("\n") else msg + "\n"
        sys.stdout.write(line)
        sys.stdout.flush()
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    return log


def _du(path: Path) -> str:
    import subprocess

    r = subprocess.run(["du", "-sh", str(path)], capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.split()[0]
    return "?"
