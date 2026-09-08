# sessionkeep

**Agent CLIs treat chat history as cache. Sessionkeep treats it as an append-only git archive.**

Claude Code, Grok, and OpenCode will silently drop transcripts. Sessionkeep harvests them on a schedule, never deletes what the CLI deleted, and commits the result to a local git repo. An optional git remote is a second copy, not a prerequisite.

v1 adapters: **Claude Code**, **Grok**, **OpenCode**. Unix only. Python 3.12+, stdlib, no runtime deps.

Full contract: [SPECIFICATION.md](SPECIFICATION.md).

## Why not rsync / iCloud / a “session sync” app

- Claude Code prunes `~/.claude/projects/**/*.jsonl`. A sync tool with `--delete` throws the archive away with the cache. Sessionkeep **never deletes destination files**.
- OpenCode is a WAL SQLite database. Checking the `.db` into git costs a full copy every day it changes (measured ~29 MB/machine/day). Sessionkeep snapshots via the SQLite backup API and writes **one JSON file per session**.
- Grok’s `index.sqlite*` is a rebuildable FTS/vector index and was measured at ~99% of `~/.grok/memory`. It is excluded.
- Paths and session ids are **host-specific**. Two machines get two branches (and two directories). They are not merged. Resume-on-another-laptop is a different product.

This is not a GUI, not a transcript publisher, and not a config-dotfiles backup.

## Install

```bash
# from a clone
uv tool install .
# after the GitHub remote exists:
# uv tool install git+https://github.com/zhongweili/sessionkeep
```

## Quick start

```bash
sessionkeep init --machine mini
# edit ~/.config/sessionkeep/config.toml — set [git].author_email if needed
sessionkeep scan
sessionkeep backup
sessionkeep status
```

Point `[archive].remote` at any git remote you own (private GitHub, a VPS bare repo, …). Push failure does **not** fail the backup; the local repo is the source of truth.

Schedule it: `recipes/launchd.plist` (macOS, e.g. 03:00) or `recipes/sessionkeep.timer` (systemd). Optional monthly encrypted snapshot of the *bare* repo: `recipes/r2-monthly.sh`.

## What is harvested

| Agent | Taken | Left behind |
|---|---|---|
| Claude Code | `projects/` jsonl, `CLAUDE.md`, `rules/`, sanitized `settings.json` | skills, agents, hooks, auth |
| Grok | `sessions/`, `memory/**/*.md`, `config.toml` | `index.sqlite*`, `auth.json` |
| OpenCode | per-session JSON from `opencode.db` | the live `.db`, `snapshot/` nested git |

Settings are scrubbed (key names **and** value shapes — a Bearer token once lived under `OTEL_EXPORTER_OTLP_HEADERS`). **Transcript bodies are not scrubbed.** Treat the archive as private.

## Layout

```
~/sessionkeep-archive/
  .git/
  sessionkeep.log
  mini/
    claude/projects/…
    grok/sessions/…
    opencode/2026-09/ses_….json
```

One directory per `machine`. One git branch per machine is the recommended topology.

## Non-goals (v1)

GUI, cross-host resume, SaaS, Windows, Codex/Gemini/Cursor adapters, transcript-body redaction, backing up memos/couchdb/dotfiles.

## License

MIT
