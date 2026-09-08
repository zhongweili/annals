# annals

**Agent CLIs treat chat history as cache. Annals treats it as an append-only git archive.**

Claude Code, Grok, and OpenCode will silently drop transcripts. Annals harvests them on a schedule, never deletes what the CLI deleted, and commits the result to a local git repo. Offsite durability is your existing system backup's job; an optional git remote is for spanning multiple machines.

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

Schedule it: `recipes/launchd.plist` (macOS, e.g. 03:00) or `recipes/annals.timer` (systemd).

## What this protects against

Three different failures, and annals only owns the first two:

| Failure | How often | Covered by |
|---|---|---|
| The CLI deletes a transcript (Claude prunes jsonl, a session vanishes) | constantly, by design | **annals** — the append-only local repo |
| You delete it (`rm -rf`, disk cleanup, a bad command) | occasionally | **annals** — old commits still have it |
| The disk dies, the laptop is stolen | rarely, total loss | **your existing system backup** |

The first two are the point. They are also the ones nothing else solves — a sync tool with `--delete` actively makes them worse.

The third one needs an off-machine copy, and you almost certainly already have one. Time Machine, Backblaze, Arq, restic, or a borg job already sweeps up `~`, and a git repo is exactly what those tools handle well: ordinary files, self-verifying, cheap to snapshot incrementally. **Annals deliberately does not reinvent offsite backup — it just produces something your backup tool already protects.**

> [!WARNING]
> **Do not put the archive in iCloud Drive, Dropbox, OneDrive, or Google Drive.** Bidirectional sync propagates deletes, which defeats the entire purpose, and concurrent writes into `.git` are a known way to corrupt a repository. Use a real backup tool, not a sync tool.

## Why git

Transcripts are append-mostly text that gets re-read months later. That shape wants four things at once, and git is the only ubiquitous store that has all four:

- **Content-addressed dedup.** Sessions get resumed, so the same transcript is re-copied in full, slightly longer, day after day. An unchanged file costs zero new bytes, and a grown one costs roughly the delta. In a synthetic 11-day resume (a session growing 460 KB → 900 KB), the packed repo was **520 KB vs 3.3 MB** of individually-gzipped dated copies — 6× less, and that was deliberately incompressible text, so real transcripts do better. Dated copies re-store the whole file every time.
- **History as a first-class question.** "What did this transcript look like before it was pruned?" is `git log --follow`. With copy-on-write files you get filenames with timestamps and have to diff them yourself.
- **Free integrity + transport.** SHA-1/256 content hashing catches bit rot, and `push`/`clone` is a mature incremental transport you don't have to write. This is what makes the optional multi-machine story ~40 lines instead of a sync engine.
- **No daemon, no schema, no lock-in.** `git log`, `git grep`, and `git show` work on the archive in ten years with no version of annals installed. The archive outliving the tool is the whole premise.

The cost is real: history is effectively immutable, so removing one transcript means rewriting history everywhere it was pushed, and a repo with millions of small files eventually needs `gc`/`maintenance`. Both are acceptable for an *archive of record*; neither would be for a scratch cache.

Alternatives, and why not:

| Instead of git | Why not here |
|---|---|
| Plain dated file copies (`YYYY/MM/session.jsonl.gz`) | Simplest, and append-only is structurally guaranteed. But no dedup across versions, no history queries, no transport. This is what [sessionkeep](https://github.com/lug-works/sessionkeep) does — a good fit for a safety net, not for a record. |
| SQLite / DuckDB | Great for query and `list`/`search`. But it's a binary blob your backup tool re-copies whole, and one corrupt page can take the archive with it. Better as a *derived index* over the git archive than as the archive. |
| `restic` / `borg` | Genuinely excellent dedup and encryption, and the right answer for whole-machine backup. But the store is opaque: no `grep` without a restore, and the tool becomes mandatory forever. |
| Object storage (S3/R2) direct | No local copy means every read is a network call, and no history semantics. Better *downstream* of git — which is what `recipes/r2-monthly.sh` does. |

If you want fast filtered lookup (`--project`, `--since`), the right move is an index built *from* the git archive, not a different archive. That's a planned addition, not a reason to change the store.

## Multiple machines (optional)

`[archive].remote` exists for **topology, not durability**: it is how two machines converge into one repo, each on its own branch. Point it at any git remote you own — a private GitHub repo, a VPS bare repo, SourceHut.

```toml
[archive]
remote = "git@github.com:YOU/annals-archive.git"
push = true
```

Push failure does **not** fail the backup; the local repo is the source of truth. Branches are never merged — see [Layout](#layout).

If you only use one machine, leave `remote` unset. Your system backup already covers the offsite case, and pushing an unredacted archive somewhere is a decision worth making deliberately: **transcript bodies are not scrubbed** (see [What is harvested](#what-is-harvested)), so the remote must be somewhere you'd be comfortable storing raw credentials.

For a monthly encrypted snapshot of a *bare* remote repo, `recipes/r2-monthly.sh` is a worked example (GPG → S3/R2 with a retention policy). It is one person's VPS topology, not a recommendation.

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

GUI, cross-host resume, SaaS, Windows, Codex/Gemini/Cursor adapters, transcript-body redaction, backing up memos/couchdb/dotfiles, and **offsite backup** — that is your system backup's job, not this tool's.

## License

MIT
