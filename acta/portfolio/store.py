"""One transactional owner of the portfolio aggregate and its revision history."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, TypeVar

T = TypeVar("T")


class Conflict(ValueError):
    """The editor's revision is no longer current."""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)

    @classmethod
    def create(cls, directory: Path, state: dict) -> Store:
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "workspace.sqlite3"
        # Exclusive creation protects another session's initialization.
        with path.open("xb"):
            pass
        path.chmod(0o600)
        try:
            db = sqlite3.connect(path)
            try:
                db.execute("CREATE TABLE workspace (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, state TEXT NOT NULL)")
                db.execute("INSERT INTO workspace VALUES (1, 0, ?)", (json.dumps(state, ensure_ascii=False),))
                db.execute("PRAGMA user_version=1")
                db.commit()
            finally:
                db.close()
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return cls(path)

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        uri = self.path.resolve().as_uri() + "?mode=rw"
        db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
        try:
            if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("Unsupported workspace schema version")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def load(db: sqlite3.Connection) -> tuple[int, dict]:
        row = db.execute("SELECT revision, state FROM workspace WHERE id=1").fetchone()
        if row is None:
            raise ValueError("Workspace state is missing")
        revision, payload = row
        return revision, json.loads(payload)

    def read(self) -> tuple[int, dict]:
        with self.transaction() as db:
            return self.load(db)

    def change(self, expected_revision: int, action: Callable[[dict], T]) -> T:
        with self.transaction(write=True) as db:
            revision, state = self.load(db)
            if revision != expected_revision:
                raise Conflict(f"Workspace changed from revision {expected_revision} to {revision}; reload before saving.")
            before = json.dumps(state, sort_keys=True, ensure_ascii=False, allow_nan=False)
            result = action(state)
            after = json.dumps(state, sort_keys=True, ensure_ascii=False, allow_nan=False)
            if before != after:
                db.execute("UPDATE workspace SET revision=?, state=? WHERE id=1", (revision + 1, after))
            return result

    def backup(self, destination: Path) -> None:
        destination = Path(destination)
        if destination.exists():
            raise ValueError("Backup destination already exists")
        with destination.open("xb"):
            pass
        destination.chmod(0o600)
        try:
            with self.transaction() as db:
                target = sqlite3.connect(destination)
                try:
                    db.backup(target)
                finally:
                    target.close()
        except Exception:
            destination.unlink(missing_ok=True)
            raise
