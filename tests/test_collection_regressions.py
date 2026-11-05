"""User-visible regressions for incremental collection and repository identity."""
import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from acta.cli import app
from acta.extractors import (
    extract_commits, extract_contributed_repos, extract_issues,
    extract_pull_requests, extract_readmes, extract_stars, extract_reviews,
)
from tests.test_extractors import FakeGitHubClient, _make_repo_node
from tests.test_cli import _mock_subprocess_run

SINCE = datetime(2026, 11, 4, tzinfo=timezone.utc)
PAGE = {"hasNextPage": False, "endCursor": None}


def commit(oid, date):
    return {"oid": oid * 40, "message": oid, "committedDate": date,
            "author": {"user": {"login": "alice"}}, "additions": 1, "deletions": 0}


def commit_client(nodes):
    return FakeGitHubClient(graphql_responses=[{"repository": {"defaultBranchRef": {
        "target": {"history": {"nodes": nodes, "pageInfo": PAGE}}}}}])


def activity(number, created, updated):
    return {"number": number, "createdAt": created, "updatedAt": updated,
            "title": f"record-{number}", "state": "OPEN", "body": "",
            "url": f"https://github.com/alice/demo/issues/{number}",
            "repository": {"nameWithOwner": "alice/demo"}}


def test_incremental_commits_preserve_history_and_deduplicate(tmp_path):
    old = commit("a", "2026-11-01T00:00:00Z")
    new = commit("b", "2026-11-05T00:00:00Z")
    repos = [{"name": "demo", "nameWithOwner": "alice/demo"}]
    extract_commits(commit_client([old]), tmp_path, "alice", repos, SINCE)
    for _ in range(2):
        records = extract_commits(commit_client([new]), tmp_path, "alice", repos, SINCE)
    assert len(records) == 2
    text = (tmp_path / "commits/2026-11.md").read_text()
    assert "aaaaaaa" in text and "bbbbbbb" in text
    assert "total: 2" in text


def test_org_repositories_keep_distinct_owners_for_every_output(tmp_path):
    nodes = []
    for owner in ["team-a", "team-b"]:
        node = _make_repo_node("demo")
        node.update(nameWithOwner=f"{owner}/demo", url=f"https://github.com/{owner}/demo")
        nodes.append(node)

    class RecordingClient(FakeGitHubClient):
        def __init__(self):
            super().__init__(graphql_responses=[{"user": {"repositories": {"nodes": nodes, "pageInfo": PAGE}}}])
            self.endpoints = []
            self.owners = []
        def rest(self, endpoint, **kwargs):
            self.endpoints.append(endpoint)
            if endpoint.endswith("/readme"):
                return {"content": base64.b64encode(endpoint.encode()).decode()}
            return {"Python": 1}
        def graphql(self, query, variables):
            if "owner" in variables:
                self.owners.append(variables["owner"])
                return {"repository": {"defaultBranchRef": None}}
            return super().graphql(query, variables)

    client = RecordingClient()
    repos = extract_contributed_repos(client, tmp_path, "alice", SINCE, exclude_names={"alice/demo"})
    extract_commits(client, tmp_path, "alice", repos, SINCE)
    extract_readmes(client, tmp_path, "alice", repos)
    assert len(repos) == 2
    assert len(list((tmp_path / "repositories").glob("*.md"))) == 2
    assert len(list((tmp_path / "readmes").glob("*.md"))) == 2
    assert client.owners == ["team-a", "team-b"]
    assert all("/alice/demo/" not in path for path in client.endpoints)


@pytest.mark.parametrize(("extract", "key"), [(extract_pull_requests, "pullRequests"), (extract_issues, "issues")])
def test_update_order_keeps_recent_items_and_refreshes_old_state(tmp_path, extract, key):
    old = activity(1, "2020-01-01T00:00:00Z", "2026-11-05T12:00:00Z")
    new = activity(2, "2026-11-05T00:00:00Z", "2026-11-05T00:00:00Z")
    client = FakeGitHubClient(graphql_responses=[{"user": {key: {"nodes": [old, new], "pageInfo": PAGE}}}])
    records = extract(client, tmp_path, "alice", SINCE)
    assert {row["number"] for row in records} == {1, 2}
    old["state"] = "CLOSED"
    client = FakeGitHubClient(graphql_responses=[{"user": {key: {"nodes": [old], "pageInfo": PAGE}}}])
    records = extract(client, tmp_path, "alice", SINCE)
    assert len(records) == 2
    assert next(row for row in records if row["number"] == 1)["state"] == "CLOSED"


def test_api_failure_preserves_all_existing_output_and_checkpoint(tmp_path):
    import subprocess
    base = tmp_path / "data"
    base.mkdir()
    (base / "profile.md").write_text("existing profile")
    (base / "metadata.json").write_text(json.dumps({"generated_at": "2026-11-01T00:00:00Z"}))
    before = {p.name: p.read_bytes() for p in base.iterdir()}
    def fail_after_auth(*args, **kwargs):
        cmd = args[0]
        if "graphql" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="API unavailable (HTTP 503)")
        return _mock_subprocess_run(*args, **kwargs)
    with patch("subprocess.run", side_effect=fail_after_auth):
        result = CliRunner().invoke(app, ["run", "--output", str(base), "--since-last-run"])
    assert result.exit_code != 0
    assert "Done!" not in result.output
    assert {p.name: p.read_bytes() for p in base.iterdir()} == before


def test_builtin_template_works_outside_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "SUMMARY.md").write_text("# Collected activity")
    result = CliRunner().invoke(app, ["analyze", "-t", "profile", "-i", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "# Collected activity" in (tmp_path / "analysis/profile.prompt.md").read_text()


def test_incremental_monthly_issues_keep_both_records(tmp_path):
    old = activity(1, "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z")
    new = activity(2, "2026-11-05T00:00:00Z", "2026-11-05T00:00:00Z")
    for node in [old, new, new]:
        client = FakeGitHubClient(graphql_responses=[{"user": {"issues": {"nodes": [node], "pageInfo": PAGE}}}])
        records = extract_issues(client, tmp_path, "alice", datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert len(records) == 2
    text = (tmp_path / "issues/2026-11.md").read_text()
    assert "record-1" in text and "record-2" in text


def test_incremental_stars_keep_same_month_history(tmp_path):
    for name in ["a/one", "b/two", "b/two"]:
        edge = {"starredAt": "2026-11-05T00:00:00Z", "node": {
            "nameWithOwner": name, "url": f"https://github.com/{name}"}}
        client = FakeGitHubClient(graphql_responses=[{"viewer": {"starredRepositories": {"edges": [edge], "pageInfo": PAGE}}}])
        records = extract_stars(client, tmp_path, "alice", SINCE)
    assert len(records) == 2
    text = (tmp_path / "stars/2026-11.md").read_text()
    assert "a/one" in text and "b/two" in text


def test_incremental_reviews_keep_same_month_history(tmp_path):
    for review_id in ["review1", "review2", "review2"]:
        node = {"occurredAt": "2026-11-05T00:00:00Z", "pullRequestReview": {
            "id": review_id, "state": "APPROVED", "body": review_id,
            "pullRequest": {"title": "PR", "number": 1, "url": "https://github.com/a/b/pull/1",
                            "repository": {"nameWithOwner": "a/b"}}}}
        client = FakeGitHubClient(graphql_responses=[{"user": {"contributionsCollection": {
            "pullRequestReviewContributions": {"nodes": [node], "pageInfo": PAGE}}}}])
        records = extract_reviews(client, tmp_path, "alice", SINCE)
    assert len(records) == 2
    text = (tmp_path / "reviews/2026-11.md").read_text()
    assert "review1" in text and "review2" in text


def test_cli_reuses_totals_and_does_not_advance_skipped_checkpoint(tmp_path):
    from acta.client import GitHubClient
    base = tmp_path / "data"
    old_checkpoint = "2026-11-01T00:00:00+00:00"
    extract_commits(commit_client([commit("a", old_checkpoint)]), base, "alice", [{"name": "demo"}], SINCE)
    (base / "metadata.json").write_text(json.dumps({"github_user": "alice", "generated_at": old_checkpoint,
        "collection_since": "2026-10-01T00:00:00+00:00", "checkpoints": {"commits": old_checkpoint}}))
    with patch("subprocess.run", side_effect=_mock_subprocess_run):
        # Keep the real activity client but use the mock's authenticated username.
        with patch.object(GitHubClient, "get_authenticated_user", return_value="alice"):
            result = CliRunner().invoke(app, ["run", "--since-last-run", "--output", str(base), "--skip-commits", "--skip-readmes"])
    assert result.exit_code == 0, result.output
    meta = json.loads((base / "metadata.json").read_text())
    assert meta["summary"]["commits"] == 1
    assert meta["checkpoints"]["commits"] == old_checkpoint
    assert "2026-11-01,Commit,alice/demo,a" in (base / "timeline.csv").read_text()
    assert "alice/demo" in (base / "SUMMARY.md").read_text()
    seen = []
    def capture(*args):
        seen.append(args[-1])
        return []
    with patch("subprocess.run", side_effect=_mock_subprocess_run), patch.object(GitHubClient, "get_authenticated_user", return_value="alice"), patch("acta.cli.extract_commits", side_effect=capture):
        result = CliRunner().invoke(app, ["run", "--since-last-run", "--output", str(base), "--skip-readmes"])
    assert result.exit_code == 0, result.output
    assert seen == [datetime.fromisoformat(old_checkpoint)]


def test_legacy_export_backfills_before_using_checkpoint(tmp_path):
    base = tmp_path / "data"
    base.mkdir()
    (base / "metadata.json").write_text(json.dumps({"generated_at": "2026-11-01T00:00:00+00:00", "period_days": 30}))
    seen = []
    def capture(*args):
        seen.append(args[-1])
        return []
    with patch("subprocess.run", side_effect=_mock_subprocess_run), patch("acta.cli.extract_commits", side_effect=capture):
        result = CliRunner().invoke(app, ["run", "--since-last-run", "--output", str(base), "--skip-readmes"])
    assert result.exit_code == 0, result.output
    assert seen == [datetime(2026, 10, 2, tzinfo=timezone.utc)]
    assert "Backfilling commits" in result.output


def test_late_failure_rolls_back_files_already_written(tmp_path):
    import subprocess
    base = tmp_path / "data"
    base.mkdir()
    (base / "profile.md").write_text("existing profile")
    (base / "metadata.json").write_text(json.dumps({"generated_at": "2026-11-01T00:00:00Z"}))
    before = {p.name: p.read_bytes() for p in base.iterdir()}
    def fail_late(*args, **kwargs):
        if "/user/orgs" in args[0]:
            raise subprocess.CalledProcessError(1, args[0], stderr="HTTP 503")
        return _mock_subprocess_run(*args, **kwargs)
    with patch("subprocess.run", side_effect=fail_late):
        result = CliRunner().invoke(app, ["run", "--output", str(base), "--skip-readmes"])
    assert result.exit_code != 0
    assert "previous output and checkpoints preserved" in result.output
    assert {p.name: p.read_bytes() for p in base.iterdir()} == before


def test_owner_filename_migration_removes_only_matching_legacy_exports(tmp_path):
    from acta.writers import write_md
    node = _make_repo_node("demo")
    write_md(tmp_path / "repositories/demo.md", {"url": node["url"]}, "old")
    write_md(tmp_path / "readmes/demo_readme.md", {"url": node["url"]}, "old")
    unrelated = tmp_path / "repositories/notes.md"
    unrelated.write_text("user notes")
    client = FakeGitHubClient(graphql_responses=[{"user": {"repositories": {"nodes": [node], "pageInfo": PAGE}}}],
        rest_responses={"/repos/user/demo/readme": {"content": base64.b64encode(b"README").decode()}})
    repos = extract_contributed_repos(client, tmp_path, "user", SINCE)
    extract_readmes(client, tmp_path, "user", repos)
    assert not (tmp_path / "repositories/demo.md").exists()
    assert not (tmp_path / "readmes/demo_readme.md").exists()
    assert (tmp_path / "repositories/user__demo.md").exists()
    assert (tmp_path / "readmes/user__demo_readme.md").exists()
    assert unrelated.read_text() == "user notes"


def test_skipping_uncached_legacy_activity_does_not_zero_its_summary(tmp_path):
    base = tmp_path / "data"
    (base / "commits").mkdir(parents=True)
    (base / "commits/2026-11.md").write_text("legacy history")
    (base / "metadata.json").write_text(json.dumps({"generated_at": "2026-11-01T00:00:00Z", "summary": {"commits": 2}}))
    before = (base / "metadata.json").read_bytes()
    with patch("subprocess.run", side_effect=_mock_subprocess_run):
        result = CliRunner().invoke(app, ["run", "--since-last-run", "--output", str(base), "--skip-commits", "--skip-readmes"])
    assert result.exit_code != 0
    assert "backfill" in result.output.lower()
    assert (base / "metadata.json").read_bytes() == before


def test_long_review_history_uses_bounded_windows_and_resets_cursors(tmp_path):
    class ReviewClient:
        rate_limit_delay = 0
        def __init__(self):
            self.calls = []
        def graphql(self, query, variables):
            self.calls.append(dict(variables))
            assert datetime.fromisoformat(variables["to"]) - datetime.fromisoformat(variables["from"]) <= timedelta(days=365)
            page = {"hasNextPage": "after" not in variables, "endCursor": "page-2"}
            return {"user": {"contributionsCollection": {"pullRequestReviewContributions": {"nodes": [], "pageInfo": page}}}}
    client = ReviewClient()
    extract_reviews(client, tmp_path, "alice", datetime(2023, 1, 1, tzinfo=timezone.utc))
    windows = [call for call in client.calls if "after" not in call]
    assert len(windows) >= 3
    assert len(client.calls) == 2 * len(windows)
    assert all(a["to"] == b["from"] for a, b in zip(windows, windows[1:]))
