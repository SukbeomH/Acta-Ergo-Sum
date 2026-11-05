"""Publish the collection-to-portfolio contract inside the existing staged output."""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from acta.portfolio.source import Snapshot, read_snapshot, seal_snapshot, validate_snapshot


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class CollectionExport:
    def __init__(self, previous: Path | None = None):
        self.resources: dict[str, dict] = {}
        self.observations: dict[str, dict] = {}
        self.subject: dict | None = None
        self.alias_index: dict[str, str] = {}
        if previous and (previous / "portfolio-source.json").exists():
            payload = read_snapshot(previous).payload
            self.resources = {r["key"]: r for r in payload["resources"]}
            self.subject = payload["subject"]
            for item in self.resources.values():
                for alias in item.get("aliases", []):
                    self.alias_index[alias] = item["key"]

    def _find(self, keys: list[str]) -> dict | None:
        matches = {key if key in self.resources else self.alias_index[key] for key in keys if key in self.resources or key in self.alias_index}
        if len(matches) > 1:
            raise ValueError("Ambiguous collection identity")
        return self.resources[next(iter(matches))] if matches else None

    def _put(self, item: dict, observed: bool) -> dict:
        old = self.resources.get(item["key"]) or self._find(item["aliases"])
        if old:
            if old["key"] != item["key"]:
                if not old["provisional"] and not item["provisional"]:
                    raise ValueError("Conflicting collection native IDs")
                if item["provisional"]:
                    item["key"], item["provisional"] = old["key"], old["provisional"]
                else:
                    old_key = old["key"]
                    self.resources.pop(old_key)
                    self.observations.pop(old_key, None)
                    item["aliases"].append(old_key)
                    for resource in self.resources.values():
                        if resource["project_key"] == old_key:
                            resource["project_key"] = item["key"]
                    if item["kind"] == "project":
                        item["project_key"] = item["key"]
            item["aliases"] = sorted(set(item["aliases"] + old.get("aliases", [])) - {item["key"]})
            if not observed:
                return old
            item["observed_at"] = timestamp()
        self.resources[item["key"]] = item
        for alias in item["aliases"]:
            self.alias_index[alias] = item["key"]
        if observed:
            item["observed_at"] = timestamp()
            self.observations[item["key"]] = {"outcome": "observed", "at": item["observed_at"]}
        return item

    def project(self, repo: dict, *, observed: bool = False, fallback: str = "") -> dict:
        name = repo.get("nameWithOwner") or (repo.get("url", "").removeprefix("https://github.com/").strip("/")) or fallback
        if "/" not in name:
            name = fallback or f"{(self.subject or {}).get('login', 'unknown')}/{repo.get('name', name)}"
        url = f"https://github.com/{name}"
        aliases = [f"github:repo:{name}", url]
        old = self._find([*aliases, f"github:{repo['id']}"] if repo.get("id") else aliases)
        native = repo.get("id")
        key = f"github:{native}" if native else old["key"] if old else aliases[0]
        fields = copy.deepcopy(old["fields"]) if old else {}
        if "description" in repo:
            fields["description"] = repo.get("description") or ""
        if "primaryLanguage" in repo:
            fields["language"] = (repo.get("primaryLanguage") or {}).get("name", "")
        visibility = "private" if repo.get("isPrivate") is True else "public" if repo.get("isPrivate") is False else old["visibility"] if old else "unknown"
        item = self._put({"key": key, "project_key": key, "kind": "project", "name": name, "locator": url,
                          "aliases": aliases, "provisional": not bool(native) if not old else old["provisional"] and not bool(native),
                          "visibility": visibility, "fields": fields, "observed_at": None}, observed)
        if observed:
            item["visibility_observed_at"] = item["observed_at"]
        return item

    def activity(self, kind: str, row: dict, *, observed: bool = False, repo: dict | None = None) -> dict:
        if kind == "commit":
            project = self.project(repo or {}, fallback=row.get("repo", ""))
            oid = row.get("oid")
            if not oid:
                # A short historical SHA is not upgraded to a full Git identity.
                oid = row.get("sha", "unknown")
            url = f"{project['locator']}/commit/{oid}"
            key = f"github:commit:{project['key']}:{oid}"
            fields = {"message": row.get("message", ""), "date": row.get("committedDate", row.get("date", ""))}
            provisional = project["provisional"] or len(oid) < 40
        else:
            repository = repo or row.get("repository") or {}
            if isinstance(repository, str):
                repository = {"nameWithOwner": repository}
            project = self.project(repository)
            url = row.get("url") or row.get("pr_url") or f"{project['locator']}/issues/{row.get('number', '')}"
            native = row.get("id")
            key = f"github:{native}" if native else f"github:{kind}:{url}" + (f"@{row.get('date', '')}" if kind == "review" else "")
            provisional = not bool(native)
            fields = {k: row.get(k) for k in ("title", "body", "state", "mergedAt", "closedAt") if k in row}
            if kind == "review":
                fields.update(pr_title=row.get("pr_title", ""), date=row.get("date", ""))
        metadata = repo if kind == "commit" else repository
        if observed and isinstance((metadata or {}).get("isPrivate"), bool):
            project["visibility"] = "private" if metadata["isPrivate"] else "public"
            project["visibility_observed_at"] = timestamp()
        return self._put({"key": key, "project_key": project["key"], "kind": kind, "name": row.get("title") or row.get("message") or kind,
                          "locator": url, "aliases": [f"github:{kind}:{url}" + (f"@{row.get('date', '')}" if kind == "review" else "")],
                          "provisional": provisional, "visibility": project["visibility"], "fields": fields, "observed_at": None}, observed)

    def observe(self, transport: str, request: str, variables: dict, data: object) -> None:
        if not isinstance(data, dict):
            return
        if transport == "rest":
            if request == "/user":
                login = data.get("login", "")
                native = data.get("node_id")
                subject = {"key": f"github:{native}" if native else f"github:user:{login}", "login": login, "provisional": not bool(native)}
                if self.subject and self.subject["key"] != subject["key"] and not (self.subject.get("provisional") and self.subject["login"].lower() == login.lower()):
                    raise ValueError("Existing collection belongs to another account")
                self.subject = subject
            return
        user = data.get("user") or {}
        if "repositories" in user:
            for repo in user["repositories"]["nodes"]:
                self.project(repo, observed=True)
        for field, kind in [("pullRequests", "pull_request"), ("issues", "issue")]:
            if field in user:
                for row in user[field]["nodes"]:
                    self.activity(kind, row, observed=True)
        reviews = (user.get("contributionsCollection") or {}).get("pullRequestReviewContributions")
        if reviews:
            for node in reviews["nodes"]:
                review = node["pullRequestReview"]
                pr = review["pullRequest"]
                row = dict(review, url=pr["url"], repository=pr["repository"], pr_title=pr["title"], date=node["occurredAt"])
                self.activity("review", row, observed=True)
        repo = data.get("repository")
        if repo and "defaultBranchRef" in repo:
            project = self.project(repo, fallback=f"{variables.get('owner', '')}/{variables.get('name', '')}")
            ref = repo.get("defaultBranchRef") or {}
            history = (ref.get("target") or {}).get("history")
            if history:
                for row in history["nodes"]:
                    author = ((row.get("author") or {}).get("user") or {}).get("login", "")
                    if author.lower() == (self.subject or {}).get("login", "").lower():
                        self.activity("commit", row, observed=True, repo={"id": repo.get("id"), "nameWithOwner": project["name"], "isPrivate": repo.get("isPrivate")})

    def finish(self, base: Path, login: str, repos: list[dict], records: dict[str, list], coverage: dict) -> Snapshot:
        for repo in repos:
            self.project(repo)
        for category, rows in records.items():
            kind = {"commits": "commit", "pull_requests": "pull_request", "issues": "issue", "reviews": "review"}[category]
            for row in rows:
                self.activity(kind, row)
        # Visibility can be checked through PR repository metadata without re-reading a cached body.
        for resource in self.resources.values():
            parent = self.resources[resource["project_key"]]
            checked = parent.get("visibility_observed_at")
            if checked:
                resource["visibility"] = parent["visibility"]
                resource["visibility_observed_at"] = checked
        payload = seal_snapshot({"schema_version": 1, "snapshot_id": uuid.uuid4().hex, "generated_at": timestamp(),
            "subject": self.subject or {"key": f"github:user:{login}", "login": login, "provisional": True},
            "coverage": coverage, "resources": list(self.resources.values()), "observations": self.observations})
        result = validate_snapshot(payload)
        (base / "portfolio-source.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result


def legacy_snapshot(base: Path) -> Snapshot:
    metadata = json.loads((base / "metadata.json").read_text(encoding="utf-8"))
    login = metadata.get("github_user")
    if not isinstance(login, str) or not login:
        raise ValueError("Legacy collection requires metadata.github_user")
    exporter = CollectionExport()
    for path in (base / "repositories").glob("*.md"):
        text = path.read_text(encoding="utf-8").split("---", 2)
        fields = dict(line.split(": ", 1) for line in text[1].splitlines() if ": " in line) if len(text) == 3 else {}
        if not fields.get("url", "").startswith("https://github.com/"):
            continue
        exporter.project({"url": fields["url"], "nameWithOwner": fields.get("name_with_owner", ""), "isPrivate": None})
    records = {}
    for category in ("commits", "pull_requests", "issues", "reviews"):
        path = base / ".records" / f"{category}.json"
        records[category] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(records[category], list) or not all(isinstance(r, dict) for r in records[category]):
            raise ValueError("Invalid legacy activity records")
    # Legacy adaptation must not write to the collection directory.
    for category, rows in records.items():
        for row in rows:
            exporter.activity({"commits": "commit", "pull_requests": "pull_request", "issues": "issue", "reviews": "review"}[category], row)
    from acta.portfolio.source import digest
    generated_at = metadata.get("generated_at") or datetime.fromtimestamp((base / "metadata.json").stat().st_mtime, timezone.utc).isoformat()
    legacy_id = digest({"subject": login, "resources": list(exporter.resources.values()), "generated_at": generated_at})
    payload = seal_snapshot({"schema_version": 1, "snapshot_id": "legacy:" + legacy_id, "generated_at": generated_at,
        "subject": {"key": f"github:user:{login}", "login": login, "provisional": True}, "legacy": True,
        "coverage": {}, "resources": list(exporter.resources.values()), "observations": {}})
    return validate_snapshot(payload)
