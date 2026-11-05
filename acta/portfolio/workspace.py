"""Revision-bound human claims, source observations and public exports."""
from __future__ import annotations

import copy
import json
import math
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from acta.portfolio.source import Snapshot, canonical, digest, read_snapshot, validate_snapshot
from acta.portfolio.store import Store

DISCLOSURES = {"public", "private", "needs_review"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identifier(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex


def _at_least(at: str | None, previous: str | None) -> bool:
    if at is None:
        return False
    current = datetime.fromisoformat(at.replace("Z", "+00:00"))
    if current.tzinfo is None:
        raise ValueError("Observation timestamps require a timezone")
    return previous is None or current >= datetime.fromisoformat(previous.replace("Z", "+00:00"))


def _update_visibility(entity: dict, visibility: str, at: str | None) -> None:
    if _at_least(at, entity.get("last_visibility_at")):
        entity.update(visibility=visibility, last_visibility_at=at)


def _append(entity: dict, payload: dict, prefix: str) -> dict:
    if entity["history"] and entity["history"][-1]["payload"] == payload:
        return entity["history"][-1]
    revision = {"id": identifier(prefix), "payload": copy.deepcopy(payload), "created_at": now()}
    entity["history"].append(revision)
    return revision


def _current(entity: dict) -> dict:
    return entity["history"][-1]


def _text(value: object, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(f"{name} must be text" + ("" if empty else " and cannot be empty"))
    return value.strip()


def _disclosure(value: object) -> str:
    if value not in DISCLOSURES:
        raise ValueError("Disclosure must be public, private or needs_review")
    return value


def _project_name(project: dict) -> str:
    return project.get("label") or project["source_name"]


def _excerpt(fields: dict) -> str:
    return "\n".join(str(fields[key]) for key in sorted(fields) if fields[key])


def _content(evidence: dict) -> dict:
    return _current(evidence)["payload"]


def _evidence_stamp(evidence: dict) -> dict:
    return {"revision": _current(evidence)["id"], "disclosure": evidence["disclosure"],
            "visibility": evidence["visibility"], "availability": evidence["availability"]}


def _claim_stamp(state: dict, claim: dict) -> str:
    payload = _current(claim)["payload"]
    return digest({"policy": 1, "claim_revision": _current(claim)["id"],
                   "evidence": {key: _evidence_stamp(state["evidence"][key]) for key in payload["evidence_ids"]}})


def _claim_errors(state: dict, claim: dict) -> list[str]:
    payload = _current(claim)["payload"]
    errors = []
    if payload["scope"] not in {"individual", "team"} or not payload["role"].strip():
        errors.append("Specify your role and individual/team scope")
    if not payload["evidence_ids"]:
        errors.append("At least one evidence item is required")
    if not payload["statement"].strip():
        errors.append("A contribution statement is required")
    # This is a review gate, not automatic semantic fact verification.
    quantitative_text = re.search(r"\d+(?:\.\d+)?\s*(?:%|ms\b|초\b|배\b)", payload["statement"])
    if payload["result_kind"] == "measured" or quantitative_text:
        metrics = payload["metrics"]
        if not metrics:
            errors.append("Measurement evidence and method are required")
        for metric in metrics:
            if not all(metric.get(k) not in (None, "", []) for k in ("value", "unit", "period", "method", "evidence_ids")):
                errors.append("Measurement requires value, unit, period, method and evidence IDs")
            elif not set(metric["evidence_ids"]).issubset(payload["evidence_ids"]):
                errors.append("Measurement evidence must be linked to this claim")
            if metric.get("comparison") and not all(metric.get(k) not in (None, "") for k in ("baseline", "conditions")):
                errors.append("Measurement comparison requires a baseline and conditions")
    return errors


def _claim_state(state: dict, claim: dict) -> str:
    if claim.get("rejected"):
        return "rejected"
    confirmation = claim.get("confirmation")
    if not confirmation:
        return "draft"
    return "confirmed" if confirmation["digest"] == _claim_stamp(state, claim) else "needs_review"


def _project_stamp(project: dict) -> str:
    return digest({"name": _project_name(project), "disclosure": project["disclosure"], "visibility": project["visibility"]})


def _block_stamp(state: dict, block: dict) -> str:
    return digest({"block": block, "claims": {b["claim_id"]: _claim_stamp(state, state["claims"][b["claim_id"]]) for b in block["bindings"]}})


def _draft_stamp(state: dict, draft: dict) -> str:
    payload = _current(draft)["payload"]
    project = state["projects"][draft["project_id"]]
    return digest({"draft_revision": _current(draft)["id"], "project": {
        "name": _project_name(project), "disclosure": project["disclosure"], "visibility": project["visibility"]},
        "claims": {binding["claim_id"]: _claim_stamp(state, state["claims"][binding["claim_id"]])
                   for block in payload["blocks"] for binding in block["bindings"]}})


def _draft_errors(state: dict, draft: dict) -> list[str]:
    errors = []
    for block in _current(draft)["payload"]["blocks"]:
        if not block["text"].strip() or not block["bindings"]:
            errors.append(f"Block {block['id']} needs text and claim links")
        for binding in block["bindings"]:
            claim = state["claims"][binding["claim_id"]]
            if binding["claim_revision"] != _current(claim)["id"] or _claim_state(state, claim) != "confirmed":
                errors.append(f"Block {block['id']} references an unreviewed or changed claim")
    return errors


@dataclass(frozen=True)
class ExportPlan:
    draft_id: str
    dependency_digest: str
    document: str
    manifest: str


class Portfolio:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        self.store = Store(self.path / "workspace.sqlite3")

    @classmethod
    def create(cls, path: Path, *, source: Path | None = None, snapshot: Snapshot | None = None) -> Portfolio:
        path = Path(path).resolve()
        source = Path(source).resolve() if source else None
        source_root = source.parent if source and source.is_file() else source
        if source_root and (path == source_root or path.is_relative_to(source_root) or source_root.is_relative_to(path)):
            raise ValueError("Collection and portfolio must use separate directories")
        state = {"source": str(source) if source else None, "subject": None, "projects": {}, "evidence": {},
                 "claims": {}, "drafts": {}, "imports": {}, "project_index": {}, "evidence_index": {}}
        result = cls(path)
        if snapshot:
            result._ingest(state, validate_snapshot(snapshot.payload).payload)
        store = Store.create(path, state)
        result.store = store
        return result

    @classmethod
    def open(cls, path: Path) -> Portfolio:
        result = cls(path)
        result.store.read()
        return result

    @property
    def revision(self) -> int:
        return self.store.read()[0]

    def collection_status(self) -> dict:
        state = self.store.read()[1]
        return {"subject": state["subject"], "source": state["source"], "collection": state.get("collection")}

    def projects(self) -> list[dict]:
        return [dict(p, name=_project_name(p)) for p in self.store.read()[1]["projects"].values()]

    def evidence(self, project_id: str | None = None) -> list[dict]:
        state = self.store.read()[1]
        return [self._evidence_view(e) for e in state["evidence"].values() if project_id is None or e["project_id"] == project_id]

    @staticmethod
    def _evidence_view(e: dict) -> dict:
        return dict(id=e["id"], project_id=e["project_id"], source_key=e["source_key"], kind=e["kind"],
                    locator=e["locator"], visibility=e["visibility"], disclosure=e["disclosure"],
                    fields=_content(e)["fields"], excerpt=_content(e)["excerpt"], observation=e["observation"],
                    last_observed_at=e["last_observed_at"], last_attempt=e.get("last_attempt"), availability=e["availability"], history_count=len(e["history"]))

    def evidence_item(self, evidence_id: str) -> dict:
        return self._evidence_view(self.store.read()[1]["evidence"][evidence_id])

    @staticmethod
    def _lookup(index: dict, entities: dict, item: dict) -> str | None:
        if item["key"] in index:
            return index[item["key"]]
        matches = {index[alias] for alias in item.get("aliases", []) if alias in index}
        if len(matches) > 1:
            raise ValueError("Ambiguous source identity")
        if matches:
            existing = entities[next(iter(matches))]
            if not existing.get("provisional") and existing["source_key"] != item["key"]:
                raise ValueError("Conflicting native source IDs")
            return existing["id"]
        return None

    @staticmethod
    def _index(index: dict, entity: dict, item: dict) -> None:
        for key in [item["key"], *item.get("aliases", [])]:
            if key in index and index[key] != entity["id"]:
                raise ValueError("Conflicting source alias")
            index[key] = entity["id"]
        entity.update(source_key=item["key"], provisional=item.get("provisional", False))

    def _ingest(self, state: dict, payload: dict, *, replay: bool = False) -> None:
        subject = state["subject"]
        incoming = payload["subject"]
        if subject and subject["key"] != incoming["key"]:
            if not (subject.get("provisional") and subject["login"].lower() == incoming["login"].lower()):
                raise ValueError("Collection belongs to a different account")
        state["subject"] = incoming
        state["legacy"] = payload.get("legacy", False)
        imported = state["imports"].get(payload["snapshot_id"])
        if imported and imported != payload["content_digest"]:
            raise ValueError("Same snapshot ID has a different digest")
        if imported and not replay:
            return
        materialize_only = bool(imported and replay)
        if not materialize_only:
            state["collection"] = {"snapshot_id": payload["snapshot_id"], "generated_at": payload["generated_at"], "coverage": payload["coverage"]}
        for item in payload["resources"]:
            if item["kind"] != "project":
                continue
            key = self._lookup(state["project_index"], state["projects"], item)
            if key is None:
                key = identifier("p")
                state["projects"][key] = {"id": key, "source_key": item["key"], "provisional": item.get("provisional", False),
                    "source_name": item["name"], "label": None, "selected": False, "reason": "", "disclosure": "needs_review",
                    "visibility": item["visibility"], "description": ""}
            proj = state["projects"][key]
            observation = payload["observations"].get(item["key"], {})
            if not materialize_only and observation.get("outcome") == "observed" and _at_least(observation.get("at"), proj.get("last_observed_at")):
                proj.update(source_name=item["name"], last_observed_at=observation["at"])
            if not materialize_only:
                checked = item.get("visibility_observed_at") or (observation.get("at") if observation.get("outcome") == "observed" else None)
                _update_visibility(proj, item["visibility"], checked)
            self._index(state["project_index"], proj, item)
        for evidence in state["evidence"].values():
            if evidence["kind"] != "manual" and not materialize_only:
                evidence["observation"] = {"outcome": "not_observed", "reason": "retained_cache"}
        for item in payload["resources"]:
            project_id = state["project_index"][item["project_key"]]
            key = self._lookup(state["evidence_index"], state["evidence"], item)
            if (key is None and not state["projects"][project_id]["selected"]) or (materialize_only and key is not None):
                continue
            observation = payload["observations"].get(item["key"], {"outcome": "not_observed", "reason": "retained_cache"})
            if key is None:
                key = identifier("e")
                state["evidence"][key] = {"id": key, "project_id": project_id, "source_key": item["key"],
                    "provisional": item.get("provisional", False), "kind": item["kind"], "history": [], "excerpt_override": None,
                    "locator": item["locator"], "visibility": item["visibility"], "disclosure": "needs_review",
                    "observation": observation, "availability": "available", "last_observed_at": item.get("observed_at")}
            e = state["evidence"][key]
            if e["project_id"] != project_id or e["kind"] != item["kind"]:
                raise ValueError("Source identity changed project or resource type")
            fresh_content = observation["outcome"] == "observed" and _at_least(observation.get("at"), e["last_observed_at"])
            if not e["history"] or fresh_content:
                fields = item["fields"]
                excerpt = e["excerpt_override"] if e["excerpt_override"] is not None else _excerpt(fields)
                _append(e, {"fields": fields, "excerpt": excerpt}, "er")
                e["locator"] = item["locator"]
            if fresh_content:
                e["last_observed_at"] = observation["at"]
            if observation["outcome"] != "not_observed" and _at_least(observation.get("at"), e.get("last_attempt", {}).get("at")):
                if observation["outcome"] in {"observed", "not_resolvable"}:
                    e["availability"] = "available" if observation["outcome"] == "observed" else "not_resolvable"
                e["last_attempt"] = observation
            checked = item.get("visibility_observed_at") or (observation.get("at") if observation["outcome"] == "observed" else None)
            _update_visibility(e, item["visibility"], checked)
            e["observation"] = observation
            self._index(state["evidence_index"], e, item)
        state["imports"][payload["snapshot_id"]] = payload["content_digest"]

    def import_collection(self, snapshot: Snapshot, expected_revision: int, *, source: Path | None = None) -> None:
        payload = validate_snapshot(snapshot.payload).payload
        if source:
            source = Path(source).resolve()
            root = source.parent if source.is_file() else source
            if root == self.path or root.is_relative_to(self.path) or self.path.is_relative_to(root):
                raise ValueError("Collection and portfolio directories must be separate")
        def action(state):
            self._ingest(state, payload)
            if source:
                state["source"] = str(source)
        self.store.change(expected_revision, action)

    def legacy_source(self) -> bool:
        return self.store.read()[1].get("legacy", False)

    def source_path(self) -> Path | None:
        value = self.store.read()[1]["source"]
        return Path(value) if value else None

    def select(self, project_id: str, reason: str, disclosure: str, expected_revision: int, *, selected: bool = True) -> None:
        reason, disclosure = _text(reason, "Selection reason"), _disclosure(disclosure)
        source = self.source_path()
        snapshot = read_snapshot(source, legacy=self.legacy_source()) if source and (source.is_file() or (source / "portfolio-source.json").exists() or self.legacy_source()) else None
        def action(state):
            project = state["projects"][project_id]
            project.update(selected=selected, reason=reason, disclosure=disclosure)
            project.setdefault("history", [])
            _append(project, {key: project[key] for key in ("label", "description", "selected", "reason", "disclosure")}, "pr")
            if snapshot:
                self._ingest(state, snapshot.payload, replay=True)
        self.store.change(expected_revision, action)

    def add_project(self, name: str, expected_revision: int) -> str:
        name = _text(name, "Project name")
        def action(state):
            key = identifier("p")
            state["projects"][key] = {"id": key, "source_key": None, "provisional": False, "source_name": name, "label": name,
                "selected": False, "reason": "", "disclosure": "needs_review", "visibility": "manual", "description": ""}
            return key
        return self.store.change(expected_revision, action)

    def edit_project(self, project_id: str, document: dict, expected_revision: int) -> None:
        label = _text(document.get("name"), "Project name")
        description = _text(document.get("description", ""), "Description", empty=True)
        disclosure = _disclosure(document.get("disclosure", "needs_review"))
        def action(state):
            project = state["projects"][project_id]
            project.update(label=label, description=description, disclosure=disclosure)
            project.setdefault("history", [])
            _append(project, {key: project[key] for key in ("label", "description", "selected", "reason", "disclosure")}, "pr")
        self.store.change(expected_revision, action)

    def edit_evidence(self, evidence_id: str, document: dict, expected_revision: int) -> None:
        disclosure = _disclosure(document.get("disclosure", "needs_review"))
        excerpt = document.get("excerpt")
        if excerpt is not None:
            excerpt = _text(excerpt, "Excerpt")
        def action(state):
            e = state["evidence"][evidence_id]
            if e["disclosure"] != disclosure:
                e.setdefault("disclosure_history", []).append({"previous": e["disclosure"], "disclosure": disclosure, "at": now()})
            e["disclosure"] = disclosure
            if excerpt is not None:
                e["excerpt_override"] = excerpt
                _append(e, {"fields": _content(e)["fields"], "excerpt": excerpt}, "er")
        self.store.change(expected_revision, action)

    def apply_probe(self, evidence_id: str, observation: dict, expected_revision: int, *, resource: dict | None = None) -> None:
        if observation.get("outcome") not in {"observed", "not_resolvable", "failed"}:
            raise ValueError("Invalid probe outcome")
        def action(state):
            e = state["evidence"][evidence_id]
            if resource is not None and observation["outcome"] == "observed" and _at_least(observation.get("at"), e["last_observed_at"]):
                if not e["provisional"] and resource["key"] != e["source_key"]:
                    raise ValueError("Native source ID changed; refusing to attach another object")
                project = state["projects"][e["project_id"]]
                if project["source_key"] != resource["project_key"]:
                    if not project["provisional"]:
                        raise ValueError("Probe returned another repository")
                    self._index(state["project_index"], project, {"key": resource["project_key"], "aliases": [project["source_key"]], "provisional": resource.get("provisional", False)})
                if _at_least(observation.get("at"), project.get("last_observed_at")):
                    from urllib.parse import urlparse
                    name = "/".join(urlparse(resource["locator"]).path.split("/")[1:3])
                    project.update(last_observed_at=observation["at"], source_name=name)
                _update_visibility(project, resource["visibility"], observation["at"])
                excerpt = e["excerpt_override"] if e["excerpt_override"] is not None else _excerpt(resource["fields"])
                _append(e, {"fields": resource["fields"], "excerpt": excerpt}, "er")
                e["locator"] = resource["locator"]
                _update_visibility(e, resource["visibility"], observation["at"])
                self._index(state["evidence_index"], e, resource)
                e["last_observed_at"] = observation["at"]
            elif observation["outcome"] == "observed" and resource is None:
                raise ValueError("Observed probes require content")
            if _at_least(observation.get("at"), e.get("last_attempt", {}).get("at")):
                if observation["outcome"] in {"observed", "not_resolvable"}:
                    e["availability"] = "available" if observation["outcome"] == "observed" else "not_resolvable"
                e["last_attempt"] = copy.deepcopy(observation)
                e["observation"] = copy.deepcopy(observation)
        self.store.change(expected_revision, action)

    def edit_claim(self, project_id: str, document: dict, expected_revision: int, *, claim_id: str | None = None) -> str:
        if not isinstance(document, dict):
            raise ValueError("Claim must be a JSON object")
        scope = document.get("scope", "unknown")
        if scope not in {"individual", "team", "unknown"}:
            raise ValueError("Invalid contribution scope")
        payload = {k: _text(document.get(k, ""), k, empty=True) for k in ("role", "problem", "action", "result", "statement")}
        payload.update(scope=scope, disclosure=_disclosure(document.get("disclosure", "needs_review")),
                       evidence_ids=document.get("evidence_ids", []), metrics=document.get("metrics", []), result_kind=document.get("result_kind", "qualitative"))
        if payload["result_kind"] not in {"qualitative", "measured"} or not isinstance(payload["evidence_ids"], list) or not all(isinstance(k, str) for k in payload["evidence_ids"]):
            raise ValueError("Invalid evidence IDs or result kind")
        if not isinstance(payload["metrics"], list) or not all(isinstance(m, dict) for m in payload["metrics"]):
            raise ValueError("Metrics must be a list of objects")
        for metric in payload["metrics"]:
            for field in ("value", "baseline"):
                value = metric.get(field)
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                    raise ValueError("Measurement values must be finite numbers")
            if "evidence_ids" in metric and (not isinstance(metric["evidence_ids"], list) or not all(isinstance(key, str) for key in metric["evidence_ids"])):
                raise ValueError("Measurement evidence IDs must be a list of strings")
        if document.get("manual_evidence") is not None and not isinstance(document["manual_evidence"], dict):
            raise ValueError("Manual evidence must be an object")
        def action(state):
            state["projects"][project_id]
            manual = document.get("manual_evidence")
            if manual and manual.get("excerpt"):
                eid = identifier("e")
                e = {"id": eid, "project_id": project_id, "source_key": None, "provisional": False, "kind": "manual", "history": [],
                    "excerpt_override": None, "locator": "", "visibility": "manual", "disclosure": _disclosure(manual.get("disclosure", "needs_review")),
                    "observation": {"outcome": "observed", "at": now(), "provenance": "self_reported"}, "availability": "available", "last_observed_at": now()}
                _append(e, {"fields": {"note": _text(manual["excerpt"], "Manual evidence")}, "excerpt": manual["excerpt"]}, "er")
                state["evidence"][eid] = e
                payload["evidence_ids"] = [*payload["evidence_ids"], eid]
            payload["evidence_ids"] = list(dict.fromkeys(payload["evidence_ids"]))
            for eid in payload["evidence_ids"]:
                if eid not in state["evidence"] or state["evidence"][eid]["project_id"] != project_id:
                    raise ValueError("Evidence must belong to this project")
            key = claim_id or identifier("c")
            if key not in state["claims"]:
                state["claims"][key] = {"id": key, "project_id": project_id, "history": [], "confirmation": None, "rejected": False}
            claim = state["claims"][key]
            if claim["project_id"] != project_id:
                raise ValueError("Claim belongs to another project")
            _append(claim, payload, "cr")
            return key
        return self.store.change(expected_revision, action)

    def claim_review(self, claim_id: str) -> dict:
        revision, state = self.store.read()
        claim = state["claims"][claim_id]
        return {"id": claim_id, "project_id": claim["project_id"], "revision": revision, "claim_revision": _current(claim)["id"],
                "claim": _current(claim)["payload"], "state": _claim_state(state, claim), "digest": _claim_stamp(state, claim),
                "evidence": [self._evidence_view(state["evidence"][key]) for key in _current(claim)["payload"]["evidence_ids"]],
                "blocking": _claim_errors(state, claim), "history_count": len(claim["history"])}

    def confirm_claim(self, claim_id: str, expected_revision: int, reviewed_digest: str) -> None:
        def action(state):
            claim = state["claims"][claim_id]
            errors = _claim_errors(state, claim)
            if errors:
                raise ValueError("; ".join(errors))
            stamp = _claim_stamp(state, claim)
            if stamp != reviewed_digest:
                raise ValueError("Review changed; inspect the claim again")
            if claim.get("confirmation", {}) and claim["confirmation"]["digest"] == stamp and not claim.get("rejected"):
                return
            claim["confirmation"] = {"digest": stamp, "at": now(), "actor": "local_user", "claim_revision": _current(claim)["id"],
                                     "evidence": {k: _evidence_stamp(state["evidence"][k]) for k in _current(claim)["payload"]["evidence_ids"]}}
            claim.setdefault("confirmations", []).append(copy.deepcopy(claim["confirmation"]))
            claim["rejected"] = False
        self.store.change(expected_revision, action)

    def reject_claim(self, claim_id: str, expected_revision: int) -> None:
        def action(state):
            claim = state["claims"][claim_id]
            claim["rejected"] = True
            claim.setdefault("decisions", []).append({"decision": "rejected", "at": now(), "actor": "local_user"})
        self.store.change(expected_revision, action)

    def reviews(self) -> list[dict]:
        state = self.store.read()[1]
        return [{"claim_id": c["id"], "project_id": c["project_id"], "state": _claim_state(state, c)} for c in state["claims"].values()]

    def create_draft(self, project_id: str, expected_revision: int) -> str:
        def action(state):
            if not state["projects"][project_id]["selected"]:
                raise ValueError("Select the project first")
            claims = [c for c in state["claims"].values() if c["project_id"] == project_id and _claim_state(state, c) == "confirmed"]
            if not claims:
                raise ValueError("No confirmed claims for this project")
            key = identifier("d")
            draft = {"id": key, "project_id": project_id, "history": [], "confirmation": None}
            blocks = [{"id": identifier("b"), "text": _current(c)["payload"]["statement"], "disclosure": _current(c)["payload"]["disclosure"],
                       "bindings": [{"claim_id": c["id"], "claim_revision": _current(c)["id"]}]} for c in claims]
            _append(draft, {"blocks": blocks}, "dr")
            state["drafts"][key] = draft
            return key
        return self.store.change(expected_revision, action)

    def drafts(self, project_id: str | None = None) -> list[dict]:
        state = self.store.read()[1]
        return [{"id": d["id"], "project_id": d["project_id"], "revision": _current(d)["id"], "history_count": len(d["history"])}
                for d in state["drafts"].values() if project_id is None or d["project_id"] == project_id]

    def history(self, kind: str, object_id: str) -> dict:
        if kind not in {"claims", "drafts"}:
            raise ValueError("History kind must be claims or drafts")
        item = self.store.read()[1][kind][object_id]
        return {"id": object_id, "revisions": item["history"], "confirmations": item.get("confirmations", []), "decisions": item.get("decisions", [])}

    def draft_document(self, draft_id: str) -> dict:
        draft = self.store.read()[1]["drafts"][draft_id]
        return {"blocks": [{"id": b["id"], "text": b["text"], "disclosure": b["disclosure"],
                            "claim_ids": [v["claim_id"] for v in b["bindings"]]} for b in _current(draft)["payload"]["blocks"]]}

    def edit_draft(self, draft_id: str, document: dict, expected_revision: int) -> None:
        if not isinstance(document, dict) or not isinstance(document.get("blocks"), list) or not document["blocks"]:
            raise ValueError("Draft requires at least one block")
        def action(state):
            draft = state["drafts"][draft_id]
            blocks = []
            for block in document["blocks"]:
                claim_ids = block.get("claim_ids", [])
                if not isinstance(claim_ids, list) or not claim_ids or not all(isinstance(c, str) for c in claim_ids):
                    raise ValueError("Each block needs claim IDs")
                bindings = []
                for key in dict.fromkeys(claim_ids):
                    if key not in state["claims"] or state["claims"][key]["project_id"] != draft["project_id"]:
                        raise ValueError("Block claims must belong to this project")
                    bindings.append({"claim_id": key, "claim_revision": _current(state["claims"][key])["id"]})
                blocks.append({"id": block.get("id") or identifier("b"), "text": _text(block.get("text"), "Block text"),
                               "disclosure": _disclosure(block.get("disclosure", "needs_review")), "bindings": bindings})
            if len({b["id"] for b in blocks}) != len(blocks):
                raise ValueError("Duplicate block IDs")
            _append(draft, {"blocks": blocks}, "dr")
        self.store.change(expected_revision, action)

    def draft_review(self, draft_id: str) -> dict:
        revision, state = self.store.read()
        draft = state["drafts"][draft_id]
        errors = _draft_errors(state, draft)
        if not draft.get("confirmation") or draft["confirmation"]["digest"] != _draft_stamp(state, draft):
            errors.append("Draft text and dependencies require review")
        return {"id": draft_id, "revision": revision, "digest": _draft_stamp(state, draft), "blocking": errors,
                "blocks": _current(draft)["payload"]["blocks"], "history_count": len(draft["history"]),
                "claims": [self.claim_review(c) for c in dict.fromkeys(v["claim_id"] for b in _current(draft)["payload"]["blocks"] for v in b["bindings"])]}

    def confirm_draft(self, draft_id: str, expected_revision: int, reviewed_digest: str) -> None:
        def action(state):
            draft = state["drafts"][draft_id]
            errors = _draft_errors(state, draft)
            if errors:
                raise ValueError("; ".join(errors))
            stamp = _draft_stamp(state, draft)
            if stamp != reviewed_digest:
                raise ValueError("Draft changed; review again")
            if draft.get("confirmation") and draft["confirmation"]["digest"] == stamp:
                return
            draft["confirmation"] = {"digest": stamp, "at": now(), "project": _project_stamp(state["projects"][draft["project_id"]]),
                                     "blocks": {b["id"]: _block_stamp(state, b) for b in _current(draft)["payload"]["blocks"]}}
            draft.setdefault("confirmations", []).append(copy.deepcopy(draft["confirmation"]))
        self.store.change(expected_revision, action)

    @staticmethod
    def _prepare(state: dict, draft_id: str, excluded: tuple[str, ...] = ()) -> ExportPlan:
        draft = state["drafts"][draft_id]
        project = state["projects"][draft["project_id"]]
        if project["disclosure"] != "public" or project["visibility"] not in {"public", "manual"}:
            raise ValueError("Project is not cleared for public disclosure")
        if not draft.get("confirmation") or draft["confirmation"].get("project") != _project_stamp(project):
            raise ValueError("Draft or project heading needs review")
        known_ids = {b["id"] for b in _current(draft)["payload"]["blocks"]}
        if not set(excluded).issubset(known_ids):
            raise ValueError("Unknown excluded block")
        blocks = [b for b in _current(draft)["payload"]["blocks"] if b["id"] not in excluded]
        if not blocks:
            raise ValueError("No blocks remain")
        manifest = {"project": _project_name(project), "draft_revision": _current(draft)["id"], "claims": [], "evidence": [], "blocks": []}
        lines = [f"# {_project_name(project)}", ""]
        seen_claims, seen_evidence = set(), set()
        for block in blocks:
            if draft["confirmation"].get("blocks", {}).get(block["id"]) != _block_stamp(state, block):
                raise ValueError(f"Block {block['id']} needs review")
            if block["disclosure"] != "public":
                raise ValueError(f"Block {block['id']} is not public")
            scope = "개인 기여"
            citations = []
            block_claims, block_evidence = [], []
            for binding in block["bindings"]:
                claim = state["claims"][binding["claim_id"]]
                payload = _current(claim)["payload"]
                if binding["claim_revision"] != _current(claim)["id"] or _claim_state(state, claim) != "confirmed" or payload["disclosure"] != "public":
                    raise ValueError(f"Block {block['id']} has an unreviewed or nonpublic claim")
                if payload["scope"] == "team":
                    scope = "팀 성과·본인 역할 확인"
                block_claims.append(_current(claim)["id"])
                if claim["id"] not in seen_claims:
                    manifest["claims"].append({"revision": _current(claim)["id"], "scope": payload["scope"], "role": payload["role"], "statement": payload["statement"],
                        "evidence_revisions": [_current(state["evidence"][key])["id"] for key in payload["evidence_ids"]]})
                    seen_claims.add(claim["id"])
                for key in payload["evidence_ids"]:
                    e = state["evidence"][key]
                    if e["disclosure"] != "public" or e["visibility"] not in {"public", "manual"}:
                        raise ValueError(f"Block {block['id']} depends on nonpublic evidence")
                    block_evidence.append(_current(e)["id"])
                    if key not in seen_evidence:
                        manifest["evidence"].append({"revision": _current(e)["id"], "kind": e["kind"], "url": e["locator"],
                            "excerpt": _content(e)["excerpt"], "observed_at": e["last_observed_at"], "availability": e["availability"],
                            "provenance": "self_reported" if e["kind"] == "manual" else "github"})
                        seen_evidence.add(key)
                    citations.append(e["locator"] or "사용자 기록")
            manifest["blocks"].append({"block_id": block["id"], "text": block["text"], "claim_revisions": list(dict.fromkeys(block_claims)),
                                       "evidence_revisions": list(dict.fromkeys(block_evidence))})
            lines.extend([f"- **{scope}**: {block['text']}", "  - 근거: " + ", ".join(dict.fromkeys(citations))])
        lines.extend(["", "근거와 확인은 함께 제공된 evidence.json의 기록 시점을 기준으로 합니다.", ""])
        return ExportPlan(draft_id, digest({"project": _project_stamp(project), "manifest": manifest, "blocks": blocks, "excluded": excluded}), "\n".join(lines), json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    def prepare_export(self, draft_id: str, *, excluded: tuple[str, ...] = ()) -> ExportPlan:
        return self._prepare(self.store.read()[1], draft_id, excluded)

    def publish_export(self, plan: ExportPlan, destination: Path, *, excluded: tuple[str, ...] = ()) -> Path:
        destination = Path(destination).resolve()
        source = self.source_path()
        root = source.parent if source and source.is_file() else source
        if root and (destination == root or destination.is_relative_to(root) or root.is_relative_to(destination)):
            raise ValueError("Export must not overlap the collection directory")
        # Validate before creating directories, and again while holding a read lock.
        if self.prepare_export(plan.draft_id, excluded=excluded) != plan:
            raise ValueError("Export dependencies changed; prepare again")
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".acta-export-", dir=destination) as temp:
            staging = Path(temp) / "bundle"
            staging.mkdir()
            for name, content in [("document.md", plan.document), ("evidence.json", plan.manifest)]:
                with (staging / name).open("w", encoding="utf-8") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            with self.store.transaction() as db:
                _, state = self.store.load(db)
                if self._prepare(state, plan.draft_id, excluded) != plan:
                    raise ValueError("Export dependencies changed before publication")
                target = destination / identifier("portfolio")
                staging.rename(target)
        return target
