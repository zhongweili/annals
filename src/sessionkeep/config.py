"""Load and write sessionkeep TOML config. Stdlib only (tomllib)."""

from __future__ import annotations

import os
import socket
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("claude", "grok", "opencode")

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "sessionkeep" / "config.toml"

DEFAULT_ROOTS = {
    "claude": Path.home() / ".claude",
    "grok": Path.home() / ".grok",
    "opencode": Path.home() / ".local" / "share" / "opencode" / "opencode.db",
}

# Detected in `scan` but not harvested in v1.
KNOWN_UNSUPPORTED = {
    "codex": Path.home() / ".codex" / "sessions",
    "gemini": Path.home() / ".gemini",
    "cursor": Path.home() / ".cursor",
}


def expand(path: str | Path) -> Path:
    return Path(os.path.expanduser(str(path))).resolve()


def default_machine() -> str:
    host = socket.gethostname().split(".")[0]
    return host or "machine"


@dataclass
class ArchiveConfig:
    path: Path
    machine: str
    branch: str
    remote: str | None = None
    remote_name: str = "origin"
    push: bool = True


@dataclass
class GitConfig:
    author_name: str | None = None
    author_email: str | None = None
    pack_window_memory: str = "64m"
    pack_size_limit: str = "256m"


@dataclass
class SourceConfig:
    kind: str
    enabled: bool = True
    root: Path | None = None

    def resolved_root(self) -> Path:
        if self.root is not None:
            return self.root
        return DEFAULT_ROOTS[self.kind]


@dataclass
class Config:
    archive: ArchiveConfig
    git: GitConfig = field(default_factory=GitConfig)
    sources: list[SourceConfig] = field(default_factory=list)
    path: Path | None = None

    def source(self, kind: str) -> SourceConfig | None:
        for s in self.sources:
            if s.kind == kind:
                return s
        return None

    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources if s.enabled]


class ConfigError(ValueError):
    pass


def load(path: Path | None = None) -> Config:
    raw_path = path or _discover()
    if raw_path is None or not raw_path.is_file():
        raise ConfigError(
            "no config found; run `sessionkeep init` or pass --config"
        )
    data = tomllib.loads(raw_path.read_text())
    cfg = parse(data)
    cfg.path = raw_path
    return cfg


def _discover() -> Path | None:
    env = os.environ.get("SESSIONKEEP_CONFIG")
    if env:
        return expand(env)
    if DEFAULT_CONFIG_PATH.is_file():
        return DEFAULT_CONFIG_PATH
    return None


def parse(data: dict) -> Config:
    arch = data.get("archive") or {}
    if "path" not in arch or "machine" not in arch:
        raise ConfigError("[archive] needs at least path and machine")
    machine = str(arch["machine"]).strip()
    if not machine:
        raise ConfigError("[archive].machine must be non-empty")
    branch = str(arch.get("branch") or machine)
    remote = arch.get("remote")
    archive = ArchiveConfig(
        path=expand(arch["path"]),
        machine=machine,
        branch=branch,
        remote=(str(remote).strip() or None) if remote else None,
        remote_name=str(arch.get("remote_name") or "origin"),
        push=bool(arch.get("push", True)),
    )
    g = data.get("git") or {}
    git = GitConfig(
        author_name=g.get("author_name"),
        author_email=g.get("author_email"),
        pack_window_memory=str(g.get("pack_window_memory") or "64m"),
        pack_size_limit=str(g.get("pack_size_limit") or "256m"),
    )
    sources: list[SourceConfig] = []
    for item in data.get("source") or []:
        kind = str(item.get("kind") or "").strip()
        if kind not in KINDS:
            raise ConfigError(f"unknown source kind: {kind!r} (v1: {KINDS})")
        root = item.get("root")
        sources.append(
            SourceConfig(
                kind=kind,
                enabled=bool(item.get("enabled", True)),
                root=expand(root) if root else None,
            )
        )
    if not sources:
        raise ConfigError("config has no [[source]] entries")
    seen = [s.kind for s in sources]
    if len(seen) != len(set(seen)):
        raise ConfigError("duplicate [[source]] kinds")
    return Config(archive=archive, git=git, sources=sources)


def dumps(cfg: Config) -> str:
    """Serialize a Config to TOML. Small enough that we skip a TOML lib."""
    a = cfg.archive
    lines = [
        "# sessionkeep config — see SPECIFICATION.md",
        "",
        "[archive]",
        f'path = "{_toml_path(a.path)}"',
        f'machine = "{a.machine}"',
        f'branch = "{a.branch}"',
    ]
    if a.remote:
        lines.append(f'remote = "{a.remote}"')
        lines.append(f'remote_name = "{a.remote_name}"')
    lines.append(f"push = {'true' if a.push else 'false'}")
    lines += ["", "[git]"]
    if cfg.git.author_name:
        lines.append(f'author_name = "{cfg.git.author_name}"')
    if cfg.git.author_email:
        lines.append(f'author_email = "{cfg.git.author_email}"')
    lines.append(f'pack_window_memory = "{cfg.git.pack_window_memory}"')
    lines.append(f'pack_size_limit = "{cfg.git.pack_size_limit}"')
    lines.append("")
    for s in cfg.sources:
        lines += [
            "[[source]]",
            f'kind = "{s.kind}"',
            f"enabled = {'true' if s.enabled else 'false'}",
        ]
        if s.root is not None:
            lines.append(f'root = "{_toml_path(s.root)}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _toml_path(p: Path) -> str:
    home = str(Path.home())
    s = str(p)
    if s.startswith(home + os.sep) or s == home:
        return "~" + s[len(home) :]
    return s


def write(cfg: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(cfg))
    cfg.path = path
