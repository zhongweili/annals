# sessionkeep

Append-only git archive for coding-agent sessions. Spec is `SPECIFICATION.md`; do not violate the four invariants there.

- Python 3.12+, stdlib only at runtime. Tests: `uv run pytest`.
- New agents = a new adapter under `src/sessionkeep/adapters/` plus a `[[source]] kind`. Do not special-case inside `cli.py`.
- Destination deletes are forbidden. `mirror_no_delete` is the primitive; do not add `shutil.rmtree` on archive contents.
- Binary sqlite does not go in git. Split into per-session text.
- Rebuildable indexes (`index.sqlite*`) stay out.
- One machine → one archive subdirectory and (recommended) one branch. No merge of working trees.
- 42plugin rescue stays in `extras/`. It is not a v1 adapter.
