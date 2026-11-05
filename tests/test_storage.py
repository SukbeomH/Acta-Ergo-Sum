"""Output publication must preserve the last complete export."""
from pathlib import Path

import pytest

from acta.storage import staged_output


def test_publication_failure_restores_previous_export(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    (base / "old.txt").write_text("previous")
    rename = Path.rename
    def fail_new_output(path, target):
        if path.name == "output":
            raise OSError("simulated publication failure")
        return rename(path, target)
    monkeypatch.setattr(Path, "rename", fail_new_output)
    with pytest.raises(OSError, match="publication failure"):
        with staged_output(base) as staged:
            (staged / "old.txt").write_text("changed")
    assert (base / "old.txt").read_text() == "previous"
    assert not (tmp_path / ".data.backup").exists()


def test_output_must_not_replace_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keep.txt").write_text("working files")
    with pytest.raises(ValueError, match="dedicated output"):
        with staged_output(tmp_path):
            pass
    assert (tmp_path / "keep.txt").read_text() == "working files"
