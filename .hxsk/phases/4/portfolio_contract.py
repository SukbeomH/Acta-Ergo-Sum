"""Portfolio design contract only. No persistence or application implementation.

Proposed callers receive immutable domain values after source decoding.
Workspace is the only owner of review, revision and export eligibility rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, NewType, Protocol

ObjectId = NewType("ObjectId", str)
Revision = NewType("Revision", str)
Digest = NewType("Digest", str)
WorkspaceRevision = NewType("WorkspaceRevision", int)


@dataclass(frozen=True)
class RemoteSource:
    provider: str
    node_id: str
    locator: str


@dataclass(frozen=True)
class CommitSource:
    provider: str
    repository_node_id: str
    full_oid: str
    locator: str


@dataclass(frozen=True)
class ProvisionalSource:
    provider: str
    locator: str


@dataclass(frozen=True)
class ManualSource:
    note_id: ObjectId


Source = RemoteSource | CommitSource | ProvisionalSource | ManualSource


@dataclass(frozen=True)
class Observed:
    at: datetime
    projection_digest: Digest
    visibility: Literal["public", "private", "unknown"]


@dataclass(frozen=True)
class NotResolvable:
    checked_at: datetime
    reason: Literal["forbidden", "missing_or_inaccessible"]


@dataclass(frozen=True)
class NotObserved:
    reason: Literal["skipped", "outside_scope", "retained_cache", "legacy_unknown"]


@dataclass(frozen=True)
class ProbeFailed:
    checked_at: datetime
    error_class: str


Observation = Observed | NotResolvable | NotObserved | ProbeFailed


@dataclass(frozen=True)
class Resource:
    source: Source
    project_source: Source
    kind: Literal["project", "commit", "pull_request", "issue", "review", "document"]
    selected_fields: tuple[tuple[str, str], ...]
    last_successful_observation: datetime | None


@dataclass(frozen=True)
class Coverage:
    category: str
    state: Literal["completed", "skipped"]
    requested_scope: str
    pagination_complete: bool


@dataclass(frozen=True)
class CollectionSnapshot:
    schema_version: Literal[1]
    snapshot_id: str
    content_digest: Digest
    subject: RemoteSource | ProvisionalSource
    generated_at: datetime
    coverage: tuple[Coverage, ...]
    resources: tuple[Resource, ...]
    observations: tuple[tuple[Source, Observation], ...]


@dataclass(frozen=True)
class ReviewInput:
    claim_revision: Revision
    evidence_revisions: tuple[Revision, ...]
    reviewed_payload_digest: Digest
    user_attestation: str


@dataclass(frozen=True)
class EvidenceReviewItem:
    revision: Revision
    source: Source
    excerpt: str
    observation: Observation
    last_successful_observation: datetime | None
    disclosure: Literal["public", "private", "needs_review"]


@dataclass(frozen=True)
class ClaimReviewView:
    workspace_revision: WorkspaceRevision
    claim_id: ObjectId
    claim_revision: Revision
    statement: str
    scope: Literal["individual", "team", "unknown"]
    role: str
    evidence_items: tuple[EvidenceReviewItem, ...]
    reviewed_payload_digest: Digest
    state: Literal["draft", "confirmed", "needs_review", "rejected"]
    blocking_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ImportReport:
    revision: WorkspaceRevision
    changed_claim_ids: tuple[ObjectId, ...]
    unobserved_source_count: int
    unresolved_sources: tuple[Source, ...]


@dataclass(frozen=True)
class ConfirmationReceipt:
    claim_revision: Revision
    reviewed_payload_digest: Digest
    confirmed_at: datetime


@dataclass(frozen=True)
class ExportPlan:
    draft_revision: Revision
    dependency_digest: Digest
    public_document: str
    public_manifest: str


@dataclass(frozen=True)
class ExportReceipt:
    bundle_path: Path
    draft_revision: Revision
    dependency_digest: Digest


class CollectionReader(Protocol):
    def read_snapshot(self, path: Path) -> CollectionSnapshot:
        """Decode one complete supported source file or fail without writes."""
        ...


class Portfolio(Protocol):
    @property
    def revision(self) -> WorkspaceRevision: ...

    def import_collection(self, snapshot: CollectionSnapshot,
                          expected_revision: WorkspaceRevision) -> ImportReport:
        """Apply observations atomically and preserve all human-authored revisions."""
        ...

    def claim_review(self, claim_id: ObjectId) -> ClaimReviewView: ...

    def confirm_claim(self, claim_id: ObjectId, expected_revision: WorkspaceRevision,
                      review: ReviewInput) -> ConfirmationReceipt:
        """Reject stale views and unsupported role, metric or disclosure assertions."""
        ...

    def create_draft(self, project_id: ObjectId,
                     expected_revision: WorkspaceRevision) -> Revision: ...

    def review_draft(self, draft_id: ObjectId, expected_revision: WorkspaceRevision,
                     reviewed_blocks_digest: Digest) -> Revision:
        """Record exact block text and claim bindings after explicit user review."""
        ...

    def prepare_export(self, draft_id: ObjectId,
                       audience: Literal["public"]) -> ExportPlan:
        """Validate every emitted block and citation through one domain policy."""
        ...

    def publish_export(self, plan: ExportPlan, destination: Path) -> ExportReceipt:
        """Revalidate dependencies, then publish a unique complete public bundle."""
        ...
