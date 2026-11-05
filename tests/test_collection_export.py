"""The public collection contract reports real observations, not merged-cache freshness."""
import json
from unittest.mock import patch

from typer.testing import CliRunner

from acta.cli import app
from acta.collection_export import CollectionExport
from acta.portfolio.source import read_snapshot
from tests.test_cli import _mock_subprocess_run


def repo(name="alice/demo", native="REPO_1"):
    return {"id": native, "nameWithOwner": name, "url": f"https://github.com/{name}", "isPrivate": False, "description": "Project"}


def test_native_ids_and_actual_observations_survive_cached_rows(tmp_path):
    exporter = CollectionExport()
    exporter.observe("rest", "/user", {}, {"login": "alice", "node_id": "USER_1"})
    row = {"id": "PR_1", "title": "Feature", "body": "Current body", "url": "https://github.com/alice/demo/pull/1",
           "state": "OPEN", "repository": repo()}
    exporter.observe("graphql", "query", {}, {"user": {"repositories": {"nodes": [repo()]}, "pullRequests": {"nodes": [row]}}})
    exporter.finish(tmp_path, "alice", [repo()], {"pull_requests": [dict(row, body="stale cache")]}, {})
    first = read_snapshot(tmp_path).payload
    evidence = next(r for r in first["resources"] if r["kind"] == "pull_request")
    assert evidence["fields"]["body"] == "Current body"
    assert evidence["key"] == "github:PR_1" and first["observations"][evidence["key"]]["outcome"] == "observed"
    second = CollectionExport(tmp_path)
    second.finish(tmp_path, "alice", [], {}, {})
    retained = read_snapshot(tmp_path).payload
    assert retained["observations"] == {}
    assert next(r for r in retained["resources"] if r["key"] == evidence["key"])["observed_at"] == evidence["observed_at"]


def test_run_publishes_versioned_snapshot_inside_output(tmp_path):
    with patch("subprocess.run", side_effect=_mock_subprocess_run):
        result = CliRunner().invoke(app, ["run", "--output", str(tmp_path / "data"), "--skip-readmes", "--days", "7"])
    assert result.exit_code == 0, result.output
    payload = read_snapshot(tmp_path / "data").payload
    assert payload["subject"]["login"] == "testuser"
    assert payload["coverage"]["commits"]["since"] < payload["generated_at"]


def test_repository_rename_keeps_identity_and_old_aliases(tmp_path):
    first = CollectionExport()
    first.project(repo(), observed=True)
    first.finish(tmp_path, "alice", [], {}, {})
    second = CollectionExport(tmp_path)
    second.project(repo("alice/renamed"), observed=True)
    second.finish(tmp_path, "alice", [], {}, {})
    projects = read_snapshot(tmp_path).payload["resources"]
    assert len(projects) == 1
    assert projects[0]["key"] == "github:REPO_1"
    assert "https://github.com/alice/demo" in projects[0]["aliases"]


def test_legacy_import_is_explicit_read_only_and_unknown(tmp_path):
    from acta.portfolio.workspace import Portfolio
    import pytest
    base = tmp_path / "old"
    (base / "repositories").mkdir(parents=True)
    (base / "metadata.json").write_text(json.dumps({"github_user": "alice", "generated_at": "2026-11-01T00:00:00+00:00"}))
    (base / "repositories/demo.md").write_text("---\nname: demo\nurl: https://github.com/alice/demo\n---\n")
    before = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
    with pytest.raises(ValueError):
        read_snapshot(base)
    legacy = read_snapshot(base, legacy=True)
    assert legacy.payload["resources"][0]["provisional"]
    assert legacy.payload["resources"][0]["observed_at"] is None
    assert {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()} == before
    portfolio = Portfolio.create(tmp_path / "portfolio", source=base, snapshot=legacy)
    project = portfolio.projects()[0]
    portfolio.select(project["id"], "legacy", "public", portfolio.revision)
    assert portfolio.evidence(project["id"])


def test_partial_pr_query_cannot_reuse_stale_public_visibility(tmp_path):
    first = CollectionExport()
    first.project(repo(), observed=True)
    first.finish(tmp_path, "alice", [], {}, {})
    latest = CollectionExport(tmp_path)
    private_repo = dict(repo(), isPrivate=True)
    row = {"id": "PR_1", "title": "Private work", "body": "Confidential", "state": "OPEN",
           "url": "https://github.com/alice/demo/pull/1", "repository": private_repo}
    latest.observe("graphql", "query", {}, {"user": {"pullRequests": {"nodes": [row]}}})
    latest.finish(tmp_path, "alice", [], {}, {})
    payload = read_snapshot(tmp_path).payload
    assert all(item["visibility"] == "private" for item in payload["resources"])
    project = next(item for item in payload["resources"] if item["kind"] == "project")
    # PR repository metadata refreshed visibility, not the retained project description.
    assert project["key"] not in payload["observations"]
