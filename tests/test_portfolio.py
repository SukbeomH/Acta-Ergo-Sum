"""Acceptance scenarios A01–A14 for the first portfolio release."""
import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from acta.cli import app

AT = "2026-11-05T00:00:00+00:00"


def resource(key="PR_1", project="REPO_1", name="alice/demo", body="Implemented cache", visibility="public"):
    return {"key": f"github:{key}", "project_key": f"github:{project}", "kind": "pull_request",
            "name": "Cache", "locator": f"https://github.com/{name}/pull/1", "aliases": [],
            "provisional": False, "visibility": visibility,
            "fields": {"title": "Cache", "body": body, "state": "MERGED"}, "observed_at": AT}


def project(key="REPO_1", name="alice/demo", visibility="public"):
    return {"key": f"github:{key}", "project_key": f"github:{key}", "kind": "project",
            "name": name, "locator": f"https://github.com/{name}", "aliases": [], "provisional": False,
            "visibility": visibility, "fields": {"description": "A project"}, "observed_at": AT}


def snapshot(tmp_path, items=None, observations=True, token="s1"):
    from acta.portfolio.source import seal_snapshot, read_snapshot
    items = items if items is not None else [project(), resource()]
    payload = {"schema_version": 1, "snapshot_id": token, "generated_at": AT,
               "subject": {"key": "github:USER_1", "login": "alice", "provisional": False},
               "coverage": {"pull_requests": {"state": "completed", "pagination_complete": True, "scope": "updated since checkpoint"}},
               "resources": items,
               "observations": {r["key"]: {"outcome": "observed", "at": AT} for r in items} if observations else {}}
    directory = tmp_path / "source"
    directory.mkdir(exist_ok=True)
    path = directory / "portfolio-source.json"
    path.write_text(json.dumps(seal_snapshot(payload)))
    return read_snapshot(directory)


@pytest.fixture
def workspace(tmp_path):
    from acta.portfolio.workspace import Portfolio
    p = Portfolio.create(tmp_path / "portfolio", source=tmp_path / "source")
    p.import_collection(snapshot(tmp_path), p.revision)
    return p


def contribution(evidence, **extra):
    return dict(scope="individual", role="Implemented and tested the cache", problem="Repeated lookups",
                action="Implemented cache", result="Repeated lookups reuse cached data", statement="Implemented cache to reuse lookups.",
                evidence_ids=[evidence], disclosure="public", result_kind="qualitative", metrics=[], **extra)


def confirmed(workspace):
    proj = workspace.projects()[0]
    workspace.select(proj["id"], "Relevant to platform roles", "public", workspace.revision)
    evidence = next(e for e in workspace.evidence(proj["id"]) if e["kind"] == "pull_request")
    workspace.edit_evidence(evidence["id"], {"disclosure": "public"}, workspace.revision)
    claim = workspace.edit_claim(proj["id"], contribution(evidence["id"]), workspace.revision)
    view = workspace.claim_review(claim)
    workspace.confirm_claim(claim, view["revision"], view["digest"])
    return proj["id"], evidence["id"], claim


def reviewed_draft(workspace):
    proj, evidence, claim = confirmed(workspace)
    draft = workspace.create_draft(proj, workspace.revision)
    view = workspace.draft_review(draft)
    workspace.confirm_draft(draft, view["revision"], view["digest"])
    return proj, evidence, claim, draft


def test_a01_same_names_and_rename_keep_selection(workspace, tmp_path):
    first = workspace.projects()[0]
    workspace.select(first["id"], "my selection", "public", workspace.revision)
    workspace.import_collection(snapshot(tmp_path, [project(name="alice/renamed"), project("REPO_2", "org/demo")], token="s2"), workspace.revision)
    assert len(workspace.projects()) == 2
    renamed = next(p for p in workspace.projects() if p["id"] == first["id"])
    assert renamed["reason"] == "my selection" and renamed["selected"]


def test_a02_retained_cache_is_not_a_new_observation(workspace, tmp_path):
    _, evidence, claim = confirmed(workspace)
    workspace.import_collection(snapshot(tmp_path, observations=False, token="s2"), workspace.revision)
    view = workspace.claim_review(claim)
    assert view["state"] == "confirmed"
    assert workspace.evidence_item(evidence)["last_observed_at"] == AT
    assert workspace.evidence_item(evidence)["observation"]["outcome"] == "not_observed"


def test_a03_observation_time_and_display_changes_do_not_invalidate(workspace, tmp_path):
    _, _, claim = confirmed(workspace)
    changed = resource()
    changed["observed_at"] = "2026-11-06T00:00:00+00:00"
    changed["locator"] = "https://github.com/alice/renamed/pull/1"
    workspace.import_collection(snapshot(tmp_path, [project(), changed], token="s2"), workspace.revision)
    assert workspace.claim_review(claim)["state"] == "confirmed"


def test_a04_changed_evidence_invalidates_only_dependents_idempotently(workspace, tmp_path):
    _, evidence, claim, draft = reviewed_draft(workspace)
    latest = snapshot(tmp_path, [project(), resource(body="Changed cache semantics")], token="s2")
    workspace.import_collection(latest, workspace.revision)
    revision = workspace.revision
    workspace.import_collection(latest, workspace.revision)
    assert workspace.revision == revision
    assert workspace.claim_review(claim)["state"] == "needs_review"
    assert workspace.draft_review(draft)["blocking"]
    assert workspace.evidence_item(evidence)["history_count"] == 2


@pytest.mark.parametrize("outcome", ["not_resolvable", "failed"])
def test_a05_probe_failure_preserves_human_content(workspace, outcome):
    _, evidence, claim = confirmed(workspace)
    before = workspace.claim_review(claim)["claim"]
    workspace.apply_probe(evidence, {"outcome": outcome, "at": AT, "reason": "HTTP 404" if outcome == "not_resolvable" else "timeout"}, workspace.revision)
    assert workspace.claim_review(claim)["claim"] == before
    assert workspace.evidence_item(evidence)["fields"]["body"] == "Implemented cache"
    assert workspace.evidence_item(evidence)["observation"]["outcome"] == outcome


def test_a06_edits_preserve_versions_and_require_review(workspace):
    proj, evidence, claim, draft = reviewed_draft(workspace)
    edited = contribution(evidence)
    edited["statement"] += " Tested invalidation."
    workspace.edit_claim(proj, edited, workspace.revision, claim_id=claim)
    assert workspace.claim_review(claim)["state"] == "needs_review"
    with pytest.raises(ValueError):
        workspace.prepare_export(draft)
    assert workspace.claim_review(claim)["history_count"] == 2
    doc = workspace.draft_document(draft)
    doc["blocks"][0]["text"] += " Edited."
    workspace.edit_draft(draft, doc, workspace.revision)
    assert workspace.draft_review(draft)["history_count"] == 2
    assert workspace.draft_review(draft)["blocking"]


def test_a07_qualitative_allowed_missing_measurement_blocked(workspace):
    proj, evidence, _ = confirmed(workspace)
    measured = contribution(evidence)
    measured.update(statement="Improved response time by 50%", result_kind="measured", metrics=[{"value": 50, "unit": "%"}])
    claim = workspace.edit_claim(proj, measured, workspace.revision)
    view = workspace.claim_review(claim)
    with pytest.raises(ValueError, match="[Mm]easurement"):
        workspace.confirm_claim(claim, view["revision"], view["digest"])


def test_a08_private_dependencies_block_document_and_manifest(workspace, tmp_path):
    _, evidence, _, draft = reviewed_draft(workspace)
    workspace.edit_evidence(evidence, {"disclosure": "private", "excerpt": "Confidential colleague: Kim"}, workspace.revision)
    with pytest.raises(ValueError):
        workspace.prepare_export(draft)
    assert not (tmp_path / "exports").exists()


def test_a09_stale_editor_conflicts_without_lost_updates(workspace):
    from acta.portfolio.store import Conflict
    proj = workspace.projects()[0]["id"]
    old = workspace.revision
    workspace.select(proj, "first", "public", old)
    with pytest.raises(Conflict):
        workspace.select(proj, "second", "public", old)
    assert workspace.projects()[0]["reason"] == "first"


def test_a10_atomic_failure_and_future_schema(workspace):
    before = workspace.revision
    with pytest.raises(RuntimeError):
        def fail(state):
            state["projects"].clear()
            raise RuntimeError("fault")
        workspace.store.change(before, fail)
    assert workspace.revision == before and workspace.projects()
    with sqlite3.connect(workspace.path / "workspace.sqlite3") as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="[Ss]chema"):
        workspace.projects()


def test_a11_prepared_export_rechecks_disclosure(workspace, tmp_path):
    _, evidence, _, draft = reviewed_draft(workspace)
    plan = workspace.prepare_export(draft)
    workspace.edit_evidence(evidence, {"disclosure": "private"}, workspace.revision)
    with pytest.raises(ValueError):
        workspace.publish_export(plan, tmp_path / "exports")
    assert not list((tmp_path / "exports").glob("*/document.md"))


def test_a12_round_trip_preserves_manual_and_source_edits(workspace, tmp_path):
    from acta.portfolio.workspace import Portfolio
    proj, evidence, claim, draft = reviewed_draft(workspace)
    manual = workspace.add_project("Manual team project", workspace.revision)
    workspace.select(manual, "old representative project", "public", workspace.revision)
    plan = workspace.prepare_export(draft)
    bundle = workspace.publish_export(plan, tmp_path / "exports")
    assert "Implemented cache" in (bundle / "document.md").read_text()
    manifest = json.loads((bundle / "evidence.json").read_text())
    assert manifest["claims"] and "https://github.com/alice/demo/pull/1" in json.dumps(manifest)
    reopened = Portfolio.open(workspace.path)
    reopened.import_collection(snapshot(tmp_path, [project(), resource(body="Changed")], token="s2"), reopened.revision)
    assert reopened.claim_review(claim)["state"] == "needs_review"
    assert reopened.claim_review(claim)["claim"]["role"] == "Implemented and tested the cache"
    assert next(p for p in reopened.projects() if p["id"] == manual)["reason"] == "old representative project"


def test_a13_snapshot_integrity_and_one_descriptor(tmp_path):
    from acta.portfolio.source import read_snapshot
    snapshot(tmp_path)
    path = tmp_path / "source/portfolio-source.json"
    document = json.loads(path.read_text())
    document["resources"][0]["name"] = "tampered"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="[Dd]igest"):
        read_snapshot(path.parent)


def test_a14_cli_available_without_external_model():
    result = CliRunner().invoke(app, ["portfolio", "--help"])
    assert result.exit_code == 0, result.output
    assert "refresh" in result.output and "export" in result.output


def test_excluded_changed_block_does_not_block_other_confirmed_claim(workspace, tmp_path):
    proj, evidence, claim = confirmed(workspace)
    other = contribution(evidence)
    other["manual_evidence"] = {"excerpt": "My separate documented implementation", "disclosure": "public"}
    other["evidence_ids"] = []
    other["statement"] = "Documented deployment instructions."
    other_claim = workspace.edit_claim(proj, other, workspace.revision)
    view = workspace.claim_review(other_claim)
    workspace.confirm_claim(other_claim, view["revision"], view["digest"])
    draft = workspace.create_draft(proj, workspace.revision)
    view = workspace.draft_review(draft)
    workspace.confirm_draft(draft, view["revision"], view["digest"])
    workspace.import_collection(snapshot(tmp_path, [project(), resource(body="Changed")], token="s2"), workspace.revision)
    blocked = next(b["id"] for b in workspace.draft_review(draft)["blocks"] if b["bindings"][0]["claim_id"] == claim)
    plan = workspace.prepare_export(draft, excluded=(blocked,))
    bundle = workspace.publish_export(plan, tmp_path / "exports", excluded=(blocked,))
    assert "Documented deployment" in (bundle / "document.md").read_text()
    assert "Implemented cache" not in (bundle / "document.md").read_text()


def test_real_two_session_revision_conflict(workspace):
    from concurrent.futures import ThreadPoolExecutor
    from acta.portfolio.store import Conflict
    from acta.portfolio.workspace import Portfolio
    revision = workspace.revision
    project_id = workspace.projects()[0]["id"]
    def save(reason):
        other = Portfolio.open(workspace.path)
        try:
            other.select(project_id, reason, "public", revision)
            return "saved"
        except Conflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, ["one", "two"])) == ["conflict", "saved"]


def test_reselect_cannot_revert_a_newer_selected_probe(workspace):
    proj, evidence, claim = confirmed(workspace)
    updated = resource(body="Newer selected-source content")
    workspace.apply_probe(evidence, {"outcome": "observed", "at": "2026-11-07T00:00:00+00:00"}, workspace.revision, resource=updated)
    workspace.select(proj, "reselected", "public", workspace.revision)
    assert workspace.evidence_item(evidence)["fields"]["body"] == "Newer selected-source content"


def test_older_collection_does_not_revert_newer_probe(workspace, tmp_path):
    _, evidence, _ = confirmed(workspace)
    workspace.apply_probe(evidence, {"outcome": "observed", "at": "2026-11-07T00:00:00+00:00"}, workspace.revision, resource=resource(body="Latest"))
    workspace.import_collection(snapshot(tmp_path, token="older-collection"), workspace.revision)
    assert workspace.evidence_item(evidence)["fields"]["body"] == "Latest"


def test_same_snapshot_id_with_resealed_changes_is_rejected(workspace, tmp_path):
    revision = workspace.revision
    forged = snapshot(tmp_path, [project(), resource(body="Forged")], token="s1")
    with pytest.raises(ValueError, match="digest"):
        workspace.import_collection(forged, revision)
    assert workspace.revision == revision


def test_one_open_descriptor_cannot_mix_replaced_input(tmp_path, monkeypatch):
    from acta.portfolio.source import read_snapshot, seal_snapshot
    snapshot(tmp_path)
    source = tmp_path / "source/portfolio-source.json"
    replacement = source.with_suffix(".next")
    newer = json.loads(source.read_text())
    newer["snapshot_id"] = "new"
    replacement.write_text(json.dumps(seal_snapshot(newer)))
    original_open = Path.open
    replaced = False
    def opening(path, *args, **kwargs):
        nonlocal replaced
        stream = original_open(path, *args, **kwargs)
        if path == source and not replaced:
            replacement.replace(source)
            replaced = True
        return stream
    monkeypatch.setattr(Path, "open", opening)
    assert read_snapshot(source).payload["snapshot_id"] == "s1"
    assert read_snapshot(source).payload["snapshot_id"] == "new"


def test_manifest_preserves_block_claim_evidence_links(workspace, tmp_path):
    _, _, _, draft = reviewed_draft(workspace)
    bundle = workspace.publish_export(workspace.prepare_export(draft), tmp_path / "exports")
    data = json.loads((bundle / "evidence.json").read_text())
    assert data["blocks"][0]["claim_revisions"] == [data["claims"][0]["revision"]]
    assert data["claims"][0]["evidence_revisions"] == [data["evidence"][0]["revision"]]


def test_publication_race_does_not_leave_partial_bundle(workspace, tmp_path, monkeypatch):
    import os
    _, evidence, _, draft = reviewed_draft(workspace)
    plan = workspace.prepare_export(draft)
    original = os.fsync
    changed = False
    def sync(fd):
        nonlocal changed
        original(fd)
        if not changed:
            changed = True
            workspace.edit_evidence(evidence, {"disclosure": "private"}, workspace.revision)
    monkeypatch.setattr(os, "fsync", sync)
    with pytest.raises(ValueError):
        workspace.publish_export(plan, tmp_path / "exports")
    assert list((tmp_path / "exports").iterdir()) == []


def test_account_change_is_rejected_atomically(workspace, tmp_path):
    from acta.portfolio.source import seal_snapshot, validate_snapshot
    data = snapshot(tmp_path, token="other-account").payload
    data["subject"] = {"key": "github:USER_2", "login": "bob", "provisional": False}
    before = workspace.revision
    with pytest.raises(ValueError, match="different account"):
        workspace.import_collection(validate_snapshot(seal_snapshot(data)), before)
    assert workspace.revision == before


def test_public_private_manual_projects_complete_refresh_cycle(tmp_path):
    from acta.portfolio.workspace import Portfolio
    data = snapshot(tmp_path, [project(), resource(), project("REPO_2", "company/private", "private"),
                               resource("PR_2", "REPO_2", "company/private", "Private colleague conversation", "private")])
    portfolio = Portfolio.create(tmp_path / "portfolio", source=tmp_path / "source", snapshot=data)
    pub, _, public_claim, draft = reviewed_draft(portfolio)
    original = portfolio.draft_document(draft)
    original["blocks"][0]["text"] += " Includes my edited wording."
    portfolio.edit_draft(draft, original, portfolio.revision)
    view = portfolio.draft_review(draft)
    portfolio.confirm_draft(draft, view["revision"], view["digest"])
    regenerated = portfolio.create_draft(pub, portfolio.revision)
    assert regenerated != draft and "edited wording" in portfolio.draft_document(draft)["blocks"][0]["text"]
    private = next(p for p in portfolio.projects() if p["name"] == "company/private")
    portfolio.select(private["id"], "Internal work", "public", portfolio.revision)
    private_evidence = next(e for e in portfolio.evidence(private["id"]) if e["kind"] == "pull_request")
    portfolio.edit_evidence(private_evidence["id"], {"disclosure": "public"}, portfolio.revision)
    private_claim = portfolio.edit_claim(private["id"], contribution(private_evidence["id"]), portfolio.revision)
    view = portfolio.claim_review(private_claim)
    portfolio.confirm_claim(private_claim, view["revision"], view["digest"])
    private_draft = portfolio.create_draft(private["id"], portfolio.revision)
    view = portfolio.draft_review(private_draft)
    portfolio.confirm_draft(private_draft, view["revision"], view["digest"])
    with pytest.raises(ValueError, match="public"):
        portfolio.prepare_export(private_draft)
    manual = portfolio.add_project("Manual team project", portfolio.revision)
    portfolio.select(manual, "Relevant offline project", "public", portfolio.revision)
    payload = contribution("unused")
    payload.update(scope="team", statement="The team delivered a deployment guide.", evidence_ids=[],
                   manual_evidence={"excerpt": "My role was writing operator steps.", "disclosure": "public"})
    manual_claim = portfolio.edit_claim(manual, payload, portfolio.revision)
    view = portfolio.claim_review(manual_claim)
    portfolio.confirm_claim(manual_claim, view["revision"], view["digest"])
    manual_draft = portfolio.create_draft(manual, portfolio.revision)
    view = portfolio.draft_review(manual_draft)
    portfolio.confirm_draft(manual_draft, view["revision"], view["digest"])
    bundle = portfolio.publish_export(portfolio.prepare_export(manual_draft), tmp_path / "exports")
    assert "팀 성과" in (bundle / "document.md").read_text()
    portfolio.import_collection(snapshot(tmp_path, [project(), resource(body="Changed source")], token="s2"), portfolio.revision)
    assert portfolio.claim_review(public_claim)["state"] == "needs_review"
    assert portfolio.claim_review(manual_claim)["state"] == "confirmed"
    assert "edited wording" in portfolio.draft_document(draft)["blocks"][0]["text"]
    view = portfolio.claim_review(public_claim)
    portfolio.confirm_claim(public_claim, view["revision"], view["digest"])
    view = portfolio.draft_review(draft)
    portfolio.confirm_draft(draft, view["revision"], view["digest"])
    bundle = portfolio.publish_export(portfolio.prepare_export(draft), tmp_path / "exports")
    assert "edited wording" in (bundle / "document.md").read_text()
    assert len(portfolio.history("claims", public_claim)["confirmations"]) == 2


def test_older_body_observation_cannot_revert_newer_privacy_check(workspace, tmp_path):
    _, evidence, _ = confirmed(workspace)
    parent = project(visibility="private")
    parent["visibility_observed_at"] = "2026-11-09T00:00:00+00:00"
    retained = resource(visibility="private")
    retained["visibility_observed_at"] = parent["visibility_observed_at"]
    workspace.import_collection(snapshot(tmp_path, [parent, retained], observations=False, token="privacy"), workspace.revision)
    workspace.apply_probe(evidence, {"outcome": "observed", "at": "2026-11-08T00:00:00+00:00"}, workspace.revision, resource=resource(body="Later body, older privacy"))
    assert workspace.evidence_item(evidence)["fields"]["body"] == "Later body, older privacy"
    assert workspace.evidence_item(evidence)["visibility"] == "private"
