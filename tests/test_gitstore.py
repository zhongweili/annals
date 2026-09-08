from pathlib import Path

from sessionkeep.config import ArchiveConfig, Config, GitConfig, SourceConfig
from sessionkeep.gitstore import commit_and_maybe_push, ensure_repo


def test_commit_when_dirty(tmp_path: Path):
    repo = tmp_path / "arc"
    cfg = Config(
        archive=ArchiveConfig(path=repo, machine="mini", branch="mini", push=False),
        git=GitConfig(author_name="sessionkeep", author_email="sk@example.com"),
        sources=[SourceConfig(kind="claude")],
    )
    ensure_repo(cfg)
    (repo / "mini").mkdir()
    (repo / "mini" / "hello.txt").write_text("hi")
    logs: list[str] = []
    r = commit_and_maybe_push(cfg, logs.append)
    assert r.committed is True
    assert r.files_changed >= 1
    r2 = commit_and_maybe_push(cfg, logs.append)
    assert r2.committed is False
