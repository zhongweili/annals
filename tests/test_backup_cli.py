"""End-to-end `backup` behaviour against a fake HOME."""

from pathlib import Path

import pytest

from annals.cli import main


def _git(repo: Path, *args: str) -> str:
    import subprocess

    r = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    return r.stdout.strip()


def _commits(repo: Path) -> int:
    out = _git(repo, "rev-list", "--count", "HEAD")
    return int(out) if out.isdigit() else 0


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude" / "projects" / "proj").mkdir(parents=True)
    (home / ".claude" / "projects" / "proj" / "s1.jsonl").write_text('{"a":1}\n')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("ANNALS_CONFIG", raising=False)

    archive = tmp_path / "arc"
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f'[archive]\npath = "{archive}"\nmachine = "mini"\npush = false\n'
        '\n[git]\nauthor_name = "t"\nauthor_email = "t@example.com"\n'
        '\n[[source]]\nkind = "claude"\nenabled = true\n'
        f'root = "{home / ".claude"}"\n'
    )
    return cfg_path, archive, home


def test_backup_commits_once_then_is_idempotent(env, capsys):
    cfg_path, archive, _ = env
    assert main(["backup", "--config", str(cfg_path)]) == 0
    assert _commits(archive) == 1

    # Nothing changed at the source, so there must be no second commit. The
    # lock and log used to live in the worktree and made every run dirty.
    assert main(["backup", "--config", str(cfg_path)]) == 0
    assert _commits(archive) == 1
    assert "no changes, skipping commit" in capsys.readouterr().out


def test_lock_and_log_are_not_in_the_worktree(env):
    cfg_path, archive, _ = env
    assert main(["backup", "--config", str(cfg_path)]) == 0
    tracked = _git(archive, "ls-files").splitlines()
    assert tracked == ["mini/claude/projects/proj/s1.jsonl"]
    assert not (archive / "annals.log").exists()
    assert not (archive / ".annals.lock").exists()


def test_new_session_produces_a_second_commit(env):
    cfg_path, archive, home = env
    assert main(["backup", "--config", str(cfg_path)]) == 0
    (home / ".claude" / "projects" / "proj" / "s2.jsonl").write_text('{"b":2}\n')
    assert main(["backup", "--config", str(cfg_path)]) == 0
    assert _commits(archive) == 2


def test_no_git_identity_fails_before_harvest(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    (home / ".claude" / "projects" / "s.jsonl").write_text("{}\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    # Isolate from the developer's real global git identity.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "empty-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "empty-gitconfig"))
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("EMAIL", raising=False)

    archive = tmp_path / "arc"
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f'[archive]\npath = "{archive}"\nmachine = "mini"\npush = false\n'
        '\n[[source]]\nkind = "claude"\nenabled = true\n'
        f'root = "{home / ".claude"}"\n'
    )
    assert main(["backup", "--config", str(cfg_path)]) == 1
    # The harvest must not have run: no half-written archive to explain.
    assert not (archive / "mini").exists()
