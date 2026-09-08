from pathlib import Path

from sessionkeep.mirror import exclude_prefixes, mirror_no_delete


def test_no_delete_keeps_dest_only_files(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "keep.jsonl").write_text("hello")
    dst.mkdir()
    (dst / "deleted-by-cli.jsonl").write_text("still here")
    st = mirror_no_delete(src, dst)
    assert st.copied == 1
    assert (dst / "keep.jsonl").read_text() == "hello"
    assert (dst / "deleted-by-cli.jsonl").read_text() == "still here"


def test_skips_identical_mtime_size(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "a.txt").write_text("x")
    mirror_no_delete(src, dst)
    st = mirror_no_delete(src, dst)
    assert st.copied == 0
    assert st.skipped == 1


def test_exclude_rebuildable_index(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "MEMORY.md").write_text("note")
    (src / "index.sqlite").write_text("blob")
    (src / "index.sqlite-wal").write_text("wal")
    dst = tmp_path / "dst"
    st = mirror_no_delete(src, dst, exclude=exclude_prefixes("index.sqlite"))
    assert (dst / "MEMORY.md").is_file()
    assert not (dst / "index.sqlite").exists()
    assert not (dst / "index.sqlite-wal").exists()
    assert st.skipped == 2


def test_unreadable_file_is_error_not_abort(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    good = src / "ok.txt"
    bad = src / "secret.txt"
    good.write_text("ok")
    bad.write_text("nope")
    bad.chmod(0)
    dst = tmp_path / "dst"
    try:
        st = mirror_no_delete(src, dst)
    finally:
        bad.chmod(0o644)
    assert (dst / "ok.txt").read_text() == "ok"
    assert st.errors >= 1
