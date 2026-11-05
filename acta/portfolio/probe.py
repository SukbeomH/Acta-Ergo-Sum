"""Recheck only explicitly selected GitHub evidence; never write collection data."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from acta.client import GitHubAPIError, GitHubClient
from acta.collection_export import CollectionExport

_NODE = """query($id: ID!) { node(id: $id) {
  id
  ... on Repository { nameWithOwner url isPrivate description primaryLanguage { name } }
  ... on PullRequest { title body state url mergedAt closedAt repository { id nameWithOwner isPrivate } }
  ... on Issue { title body state url closedAt repository { id nameWithOwner isPrivate } }
  ... on PullRequestReview { body state createdAt pullRequest { title url repository { id nameWithOwner isPrivate } } }
} }"""


def probe(evidence: dict, client: GitHubClient) -> tuple[dict, dict | None]:
    at = datetime.now(timezone.utc).isoformat()
    exporter = CollectionExport()
    kind, key = evidence["kind"], evidence["source_key"]
    try:
        if key and key.startswith("github:") and not key.startswith(("github:repo:", "github:commit:", "github:pull_request:", "github:issue:", "github:review:")):
            data = client.graphql(_NODE, {"id": key.removeprefix("github:")})
            row = data.get("node")
            if row is None:
                return {"outcome": "not_resolvable", "at": at, "reason": "missing_or_inaccessible"}, None
            if kind == "project":
                item = exporter.project(row, observed=True)
            else:
                if kind == "review":
                    pr = row["pullRequest"]
                    row = dict(row, url=pr["url"], repository=pr["repository"], pr_title=pr["title"], date=row["createdAt"])
                item = exporter.activity(kind, row, observed=True)
        else:
            url = urlparse(evidence["locator"])
            match = re.fullmatch(r"/([\w.-]+)/([\w.-]+)(?:/(pull|issues|commit)/(\w+))?/?", url.path)
            if url.scheme != "https" or url.hostname != "github.com" or not match:
                raise ValueError("Selected evidence has no supported GitHub locator")
            owner, name, route, number = match.groups()
            repo = client.rest(f"/repos/{owner}/{name}")
            repository = {"id": repo.get("node_id"), "nameWithOwner": repo["full_name"], "isPrivate": repo["private"], "description": repo.get("description")}
            if kind == "project":
                item = exporter.project(repository, observed=True)
            elif kind == "commit" and route == "commit":
                row = client.rest(f"/repos/{owner}/{name}/commits/{number}")
                item = exporter.activity("commit", {"oid": row["sha"], "message": row["commit"]["message"], "committedDate": row["commit"]["committer"]["date"]}, observed=True, repo=repository)
            elif kind in {"pull_request", "issue"}:
                endpoint = "pulls" if kind == "pull_request" else "issues"
                row = client.rest(f"/repos/{owner}/{name}/{endpoint}/{number}")
                normalized = {"id": row["node_id"], "title": row["title"], "body": row.get("body") or "", "state": "MERGED" if row.get("merged_at") else row["state"].upper(),
                              "url": row["html_url"], "mergedAt": row.get("merged_at"), "closedAt": row.get("closed_at"), "repository": repository}
                item = exporter.activity(kind, normalized, observed=True)
            else:
                raise ValueError("Legacy review needs a native ID; recollect or attach a manual note")
        return {"outcome": "observed", "at": at}, item
    except GitHubAPIError as exc:
        message = str(exc)
        inaccessible = "rate limit" not in message.lower() and any(tag in message for tag in ("HTTP 404", "HTTP 403", "NOT_FOUND", "FORBIDDEN"))
        return {"outcome": "not_resolvable" if inaccessible else "failed", "at": at,
                "reason": "missing_or_inaccessible" if inaccessible else "request_failed"}, None
