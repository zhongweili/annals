from pathlib import Path

import pytest

from annals.config import ConfigError, dumps, parse


def test_parse_minimal():
    cfg = parse(
        {
            "archive": {"path": "~/annals-archive", "machine": "mini"},
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


def _cfg(tmp_path: Path, **archive):
    return parse(
        {
            "archive": {"path": str(tmp_path / "arc"), "machine": "mini", **archive},
            "source": [{"kind": "claude"}],
        }
    )


def test_state_dir_defaults_outside_archive(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = cfg.archive.resolved_state_dir()
    assert cfg.archive.path not in state.parents
    assert state != cfg.archive.path


def test_state_dir_inside_archive_rejected(tmp_path: Path):
    with pytest.raises(ConfigError, match="must not be inside"):
        _cfg(tmp_path, state_dir=str(tmp_path / "arc" / "state"))


def test_state_dir_equal_to_archive_rejected(tmp_path: Path):
    with pytest.raises(ConfigError, match="must not be inside"):
        _cfg(tmp_path, state_dir=str(tmp_path / "arc"))


def test_state_dir_override_roundtrips(tmp_path: Path):
    cfg = _cfg(tmp_path, state_dir=str(tmp_path / "st"))
    assert cfg.archive.resolved_state_dir() == tmp_path / "st"
    assert "state_dir" in dumps(cfg)


def test_dumps_scaffolds_commented_author_email(tmp_path: Path):
    # init must leave a line to uncomment; a bare [git] block told users to
    # "edit author_email" when no such key existed.
    text = dumps(_cfg(tmp_path))
    assert '# author_email = "you@example.com"' in text


def test_load_reports_malformed_toml(tmp_path: Path):
    from annals.config import load

    bad = tmp_path / "config.toml"
    bad.write_text("[archive]\n[archive]\n")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load(bad)
