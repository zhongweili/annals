# annals

**Agent CLIs treat chat history as cache. Annals treats it as an append-only git archive.**

Claude Code, Grok, and OpenCode will silently drop transcripts. Annals harvests them on a schedule, never deletes what the CLI deleted, and commits the result to a local git repo. An optional git remote is a second copy, not a prerequisite.

v1 adapters: **Claude Code**, **Grok**, **OpenCode**. Unix only. Python 3.12+, stdlib, no runtime deps.

Full contract: [SPECIFICATION.md](SPECIFICATION.md).

## Why not rsync / iCloud / a “session sync” app

- Claude Code prunes `~/.claude/projects/**/*.jsonl`. A sync tool with `--delete` throws the archive away with the cache. Annals **never deletes destination files**.
- OpenCode is a WAL SQLite database. Checking the `.db` into git costs a full copy every day it changes (measured ~29 MB/machine/day). Annals snapshots via the SQLite backup API and writes **one JSON file per session**.
- Grok’s `index.sqlite*` is a rebuildable FTS/vector index and was measured at ~99% of `~/.grok/memory`. It is excluded.
- Paths and session ids are **host-specific**. Two machines get two branches (and two directories). They are not merged. Resume-on-another-laptop is a different product.

This is not a GUI, not a transcript publisher, and not a config-dotfiles backup.

## Install

```bash
# from a clone
uv tool install .
# after the GitHub remote exists:
# uv tool install git+https://github.com/zhongweili/annals
```

## Quick start

```bash
annals init --machine mini
# init tells you if this machine has no git identity — backup cannot commit
# without one. Either `git config --global user.email you@example.com` or
# uncomment [git].author_email in ~/.config/annals/config.toml.
annals scan
annals backup
annals status
```

Point `[archive].remote` at any git remote you own (private GitHub, a VPS bare repo, …). Push failure does **not** fail the backup; the local repo is the source of truth.

Schedule it: `recipes/launchd.plist` (macOS, e.g. 03:00) or `recipes/annals.timer` (systemd). Optional monthly encrypted snapshot of the *bare* repo: `recipes/r2-monthly.sh`.

## What is harvested

| Agent | Taken | Left behind |
|---|---|---|
| Claude Code | `projects/` jsonl, `CLAUDE.md`, `rules/`, sanitized `settings.json` | skills, agents, hooks, auth |
| Grok | `sessions/`, `memory/**/*.md`, `config.toml` | `index.sqlite*`, `auth.json` |
| OpenCode | per-session JSON from `opencode.db` | the live `.db`, `snapshot/` nested git |

Settings are scrubbed (key names **and** value shapes — a Bearer token once lived under `OTEL_EXPORTER_OTLP_HEADERS`). **Transcript bodies are not scrubbed.** Treat the archive as private.

## Layout

```
~/annals-archive/          # git repo — harvested data only
  .git/
  mini/
    claude/projects/…
    grok/sessions/…
    opencode/2026-09/ses_….json

~/.local/state/annals/mini/   # operational state, never committed
  annals.lock
  annals.log
```

One directory per `machine`. One git branch per machine is the recommended topology.

The lock and log stay out of the worktree on purpose: inside it, `git add -A` picks them up and every run commits even when no session changed. Override with `[archive].state_dir`; pointing it inside the archive is rejected.

## Non-goals (v1)

GUI, cross-host resume, SaaS, Windows, Codex/Gemini/Cursor adapters, transcript-body redaction, backing up memos/couchdb/dotfiles.

## License

MIT
