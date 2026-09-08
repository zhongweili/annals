import json
from pathlib import Path

from sessionkeep.adapters.claude import ADAPTER
from sessionkeep.config import SourceConfig


def test_harvest_keeps_deleted_transcript(tmp_path: Path):
    live = tmp_path / "claude"
    projects = live / "projects" / "demo"
    projects.mkdir(parents=True)
    (projects / "abc.jsonl").write_text('{"role":"user"}\n')
    (live / "settings.json").write_text(
        json.dumps({"env": {"OPENAI_API_KEY": "sk-" + "x" * 20}})
    )
    dest = tmp_path / "archive" / "claude"
    ADAPTER.harvest(SourceConfig(kind="claude", root=live), dest, lambda m: None)
    # CLI deletes the live transcript.
    (projects / "abc.jsonl").unlink()
    ADAPTER.harvest(SourceConfig(kind="claude", root=live), dest, lambda m: None)
    assert (dest / "projects" / "demo" / "abc.jsonl").is_file()
    sanitized = json.loads((dest / "settings.sanitized.json").read_text())
    assert "sk-" not in json.dumps(sanitized)
