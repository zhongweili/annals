from pathlib import Path

import pytest

from sessionkeep.config import ConfigError, dumps, parse


def test_parse_minimal():
    cfg = parse(
        {
            "archive": {"path": "~/sessionkeep-archive", "machine": "mini"},
            "source": [{"kind": "claude"}],
        }
    )
    assert cfg.archive.machine == "mini"
    assert cfg.archive.branch == "mini"
    assert cfg.sources[0].kind == "claude"
    assert cfg.sources[0].enabled is True


def test_unknown_kind_rejected():
    with pytest.raises(ConfigError, match="unknown source"):
        parse(
            {
                "archive": {"path": "/tmp/a", "machine": "x"},
                "source": [{"kind": "codex"}],
            }
        )


def test_roundtrip_toml(tmp_path: Path):
    cfg = parse(
        {
            "archive": {
                "path": str(tmp_path / "arc"),
                "machine": "mini",
                "branch": "mini-master",
                "remote": "git@example.com:u/r.git",
            },
            "source": [
                {"kind": "claude", "enabled": True},
                {"kind": "grok", "enabled": False},
                {"kind": "opencode"},
            ],
        }
    )
    text = dumps(cfg)
    assert 'machine = "mini"' in text
    assert "[[source]]" in text
    assert 'kind = "grok"' in text
    assert "enabled = false" in text


def test_duplicate_kinds():
    with pytest.raises(ConfigError, match="duplicate"):
        parse(
            {
                "archive": {"path": "/tmp/a", "machine": "x"},
                "source": [{"kind": "claude"}, {"kind": "claude"}],
            }
        )
