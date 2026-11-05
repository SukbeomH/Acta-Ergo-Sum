"""Decode one versioned collection file; never infer deletion from absence."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def seal_snapshot(payload: dict) -> dict:
    payload = {k: v for k, v in payload.items() if k != "content_digest"}
    return dict(payload, content_digest=digest(payload))


@dataclass(frozen=True)
class Snapshot:
    payload: dict


def _timestamp(value: object) -> None:
    if not isinstance(value, str) or datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("Observation timestamps require a timezone")


def validate_snapshot(value: object) -> Snapshot:
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported collection schema version")
    expected = seal_snapshot(value)["content_digest"]
    if value.get("content_digest") != expected:
        raise ValueError("Snapshot digest mismatch")
    if not isinstance(value.get("snapshot_id"), str) or not value["snapshot_id"]:
        raise ValueError("Missing snapshot ID")
    _timestamp(value.get("generated_at"))
    subject = value.get("subject")
    if not isinstance(subject, dict) or not all(isinstance(subject.get(k), str) and subject[k] for k in ("key", "login")):
        raise ValueError("Missing collection subject")
    if not isinstance(value.get("coverage"), dict) or not isinstance(value.get("observations"), dict):
        raise ValueError("Invalid coverage or observations")
    if not isinstance(subject.get("provisional"), bool):
        raise ValueError("Invalid subject identity provenance")
    for coverage in value["coverage"].values():
        if not isinstance(coverage, dict) or coverage.get("state") not in {"completed", "skipped"} or not isinstance(coverage.get("pagination_complete"), bool):
            raise ValueError("Invalid category coverage")
    resources = value.get("resources")
    if not isinstance(resources, list):
        raise ValueError("Invalid collection resources")
    keys: set[str] = set()
    project_keys: set[str] = set()
    aliases: dict[str, str] = {}
    for item in resources:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k] for k in ("key", "project_key", "kind", "name", "locator")):
            raise ValueError("Invalid resource identity")
        if item["key"] in keys:
            raise ValueError("Duplicate resource identity")
        keys.add(item["key"])
        if item["kind"] == "project":
            project_keys.add(item["key"])
            if item["project_key"] != item["key"]:
                raise ValueError("Project identity must be self-referencing")
        if not isinstance(item.get("provisional"), bool):
            raise ValueError("Invalid identity provenance")
        if item.get("kind") not in {"project", "commit", "pull_request", "issue", "review", "document"}:
            raise ValueError("Unsupported resource kind")
        if item.get("visibility") not in {"public", "private", "unknown"} or not isinstance(item.get("fields"), dict):
            raise ValueError("Invalid resource content or visibility")
        url = urlparse(item["locator"])
        if url.scheme != "https" or url.hostname != "github.com" or url.username or url.password:
            raise ValueError("Collection locators must be GitHub HTTPS URLs")
        if item.get("observed_at") is not None:
            _timestamp(item["observed_at"])
        if item.get("visibility_observed_at") is not None:
            _timestamp(item["visibility_observed_at"])
        if not isinstance(item.get("aliases", []), list) or not all(isinstance(a, str) for a in item.get("aliases", [])):
            raise ValueError("Invalid source aliases")
        for alias in item.get("aliases", []):
            if alias in aliases and aliases[alias] != item["key"]:
                raise ValueError("Ambiguous source alias")
            aliases[alias] = item["key"]
    if any(alias in keys and alias != key for alias, key in aliases.items()):
        raise ValueError("Alias conflicts with another resource identity")
    for item in resources:
        if item["project_key"] not in project_keys:
            raise ValueError("Resource references an unknown project")
    for key, observation in value["observations"].items():
        if key not in keys or not isinstance(observation, dict) or observation.get("outcome") not in {"observed", "not_observed", "not_resolvable", "failed"}:
            raise ValueError("Invalid source observation")
        if observation.get("outcome") == "observed" or observation.get("at"):
            _timestamp(observation.get("at"))
    return Snapshot(json.loads(canonical(value)))


def read_snapshot(path: Path, *, legacy: bool = False) -> Snapshot:
    path = Path(path).resolve()
    if path.is_dir():
        path = path / "portfolio-source.json"
    if legacy and not path.exists():
        from acta.collection_export import legacy_snapshot
        return legacy_snapshot(path.parent)
    for attempt in range(3):
        try:
            with path.open(encoding="utf-8") as stream:
                value = json.load(stream)
            return validate_snapshot(value)
        except FileNotFoundError:
            if attempt == 2:
                raise ValueError(f"Collection input not found: {path}. Run acta run or explicitly use --legacy.") from None
            time.sleep(0.05)
    raise AssertionError("unreachable")
