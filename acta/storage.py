"""Durable activity records and staged output publication."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def load_records(base: Path, category: str) -> list[dict[str, Any]]:
    path = base / ".records" / f"{category}.json"
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError(f"Invalid activity cache: {path}")
    return records


def merge_records(
    base: Path, category: str, incoming: list[dict], key: Callable[[dict], Any],
) -> list[dict]:
    """Keep history, replacing records with the same stable identity on retries."""
    records = {key(row): row for row in load_records(base, category)}
    records.update((key(row), row) for row in incoming)
    merged = list(records.values())
    path = base / ".records" / f"{category}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return merged


@contextmanager
def staged_output(base: Path) -> Iterator[Path]:
    """Publish only completed runs; restore the last export if publication fails."""
    base = base.resolve()
    if base == Path.cwd() or base in Path.cwd().parents:
        raise ValueError("Choose a dedicated output directory, not the working directory or its parents.")
    base.parent.mkdir(parents=True, exist_ok=True)
    backup = base.with_name(f".{base.name}.backup")
    if backup.exists():
        raise ValueError(f"Unresolved output backup: {backup}; restore it before collecting again.")
    with tempfile.TemporaryDirectory(prefix=f".{base.name}-", dir=base.parent) as temp:
        staged = Path(temp) / "output"
        if base.exists():
            shutil.copytree(base, staged)
        else:
            staged.mkdir()
        yield staged
        if base.exists():
            base.rename(backup)
        try:
            staged.rename(base)
        except OSError:
            if backup.exists():
                backup.rename(base)
            raise
        if backup.exists():
            shutil.rmtree(backup)
