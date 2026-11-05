"""Local portfolio commands. Editors and probes run outside SQLite transactions."""
from __future__ import annotations

import functools
import json
import os
import shlex
import subprocess
import tempfile
import sqlite3
from pathlib import Path
from typing import Callable

import typer

from acta.portfolio.source import read_snapshot
from acta.portfolio.workspace import Portfolio, identifier

app = typer.Typer(help="Review evidence, preserve contribution drafts and export a local portfolio.", no_args_is_help=True)
claims = typer.Typer(no_args_is_help=True)
drafts = typer.Typer(no_args_is_help=True)
evidence_commands = typer.Typer(no_args_is_help=True)
app.add_typer(claims, name="claim")
app.add_typer(drafts, name="draft")
app.add_typer(evidence_commands, name="evidence")


def safe(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError, KeyError, StopIteration, sqlite3.Error) as exc:
            typer.echo(f"✗ {exc}", err=True)
            raise typer.Exit(1) from exc
    return wrapped


def show(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


def opened(ctx: typer.Context) -> Portfolio:
    return Portfolio.open(ctx.find_root().obj["portfolio_path"])


@app.callback()
def configure(ctx: typer.Context, workspace: Path = typer.Option(Path("./portfolio"), "--workspace", "-w")):
    ctx.find_root().obj = {"portfolio_path": workspace.resolve()}


@app.command("init")
@safe
def initialize(ctx: typer.Context, source: Path | None = typer.Option(None, "--source"),
               workspace: Path | None = typer.Option(None, "--workspace", "-w"), legacy: bool = typer.Option(False, "--legacy")):
    """Create a separate workspace. Omit --source for manual projects only."""
    snapshot = read_snapshot(source, legacy=legacy) if source else None
    path = workspace.resolve() if workspace else ctx.find_root().obj["portfolio_path"]
    portfolio = Portfolio.create(path, source=source, snapshot=snapshot)
    typer.echo(f"Workspace: {portfolio.path}\nRevision: {portfolio.revision}")
    show({**portfolio.collection_status(), "projects": portfolio.projects()})


@app.command("projects")
@safe
def projects(ctx: typer.Context):
    """List candidates, selections and stable local IDs."""
    portfolio = opened(ctx)
    show({**portfolio.collection_status(), "projects": portfolio.projects()})


@app.command("select")
@safe
def select(ctx: typer.Context, project_id: str, reason: str = typer.Option(..., "--reason"),
           disclosure: str = typer.Option("needs_review", "--disclosure"), exclude: bool = typer.Option(False, "--exclude"),
           revision: int | None = typer.Option(None, "--revision")):
    portfolio = opened(ctx)
    portfolio.select(project_id, reason, disclosure, portfolio.revision if revision is None else revision, selected=not exclude)
    show(portfolio.projects())


@app.command("add-project")
@safe
def add_project(ctx: typer.Context, name: str = typer.Option(..., "--name")):
    portfolio = opened(ctx)
    typer.echo(portfolio.add_project(name, portfolio.revision))


def edit_text(initial: str) -> str | None:
    """Use the user's editor without invoking a shell or adding a dependency."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "vi")
    command = shlex.split(editor, posix=os.name != "nt")
    if not command:
        raise ValueError("EDITOR or VISUAL must name an editor")
    with tempfile.TemporaryDirectory(prefix="acta-edit-") as directory:
        path = Path(directory) / "document.json"
        path.write_text(initial, encoding="utf-8")
        path.chmod(0o600)
        result = subprocess.run([*command, str(path)], check=False)
        return path.read_text(encoding="utf-8") if result.returncode == 0 else None


def save_edit(portfolio: Portfolio, initial: dict, file: Path | None, expected: int | None, save: Callable):
    revision = portfolio.revision if expected is None else expected
    raw = file.read_text(encoding="utf-8") if file else edit_text(json.dumps(initial, ensure_ascii=False, indent=2))
    if raw is None:
        raise ValueError("Editing cancelled; nothing changed")
    try:
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError("Editor content must be a JSON object")
        return save(document, revision)
    except (ValueError, KeyError, sqlite3.Error):
        recovery = portfolio.path / "edits"
        recovery.mkdir(exist_ok=True)
        recovery.chmod(0o700)
        path = recovery / f"{identifier('edit')}.json"
        path.write_text(raw, encoding="utf-8")
        path.chmod(0o600)
        typer.echo(f"Your proposed edit is preserved at {path}", err=True)
        raise


@app.command("edit-project")
@safe
def edit_project(ctx: typer.Context, project_id: str, file: Path | None = typer.Option(None, "--file"), revision: int | None = typer.Option(None, "--revision")):
    portfolio = opened(ctx)
    revision = portfolio.revision if revision is None else revision
    project = next(p for p in portfolio.projects() if p["id"] == project_id)
    save_edit(portfolio, {k: project[k] for k in ("name", "description", "disclosure")}, file, revision,
              lambda document, expected: portfolio.edit_project(project_id, document, expected))


@evidence_commands.command("list")
@safe
def evidence_list(ctx: typer.Context, project: str | None = typer.Option(None, "--project")):
    show(opened(ctx).evidence(project))


@evidence_commands.command("edit")
@safe
def evidence_edit(ctx: typer.Context, evidence_id: str, file: Path | None = typer.Option(None, "--file"), revision: int | None = typer.Option(None, "--revision")):
    portfolio = opened(ctx)
    revision = portfolio.revision if revision is None else revision
    evidence = portfolio.evidence_item(evidence_id)
    show(evidence)
    save_edit(portfolio, {k: evidence[k] for k in ("excerpt", "disclosure")}, file, revision,
              lambda document, expected: portfolio.edit_evidence(evidence_id, document, expected))


@claims.command("edit")
@safe
def claim_edit(ctx: typer.Context, project: str = typer.Option(..., "--project"), claim_id: str | None = typer.Option(None, "--claim"),
               file: Path | None = typer.Option(None, "--file"), revision: int | None = typer.Option(None, "--revision")):
    portfolio = opened(ctx)
    revision = portfolio.revision if revision is None else revision
    initial = portfolio.claim_review(claim_id)["claim"] if claim_id else {
        "scope": "unknown", "role": "", "problem": "", "action": "", "result": "", "statement": "",
        "evidence_ids": [], "manual_evidence": {"excerpt": "", "disclosure": "needs_review"},
        "result_kind": "qualitative", "metrics": [], "disclosure": "needs_review"}
    show(portfolio.evidence(project))
    result = save_edit(portfolio, initial, file, revision,
                       lambda document, expected: portfolio.edit_claim(project, document, expected, claim_id=claim_id))
    typer.echo(result)


@claims.command("review")
@safe
def claim_review(ctx: typer.Context, claim_id: str, display_only: bool = typer.Option(False, "--show"),
                 approve: str | None = typer.Option(None, "--approve"), revision: int | None = typer.Option(None, "--revision")):
    portfolio = opened(ctx)
    view = portfolio.claim_review(claim_id)
    show(view)
    if display_only:
        return
    if approve is None and not typer.confirm("본문, 본인 역할, 수치 근거와 공개 범위를 확인했습니까?"):
        return
    portfolio.confirm_claim(claim_id, view["revision"] if revision is None else revision, approve or view["digest"])
    typer.echo("Claim confirmed for the exact reviewed revision.")


@claims.command("reject")
@safe
def reject_claim(ctx: typer.Context, claim_id: str):
    portfolio = opened(ctx)
    portfolio.reject_claim(claim_id, portfolio.revision)


@drafts.command("create")
@safe
def draft_create(ctx: typer.Context, project: str = typer.Option(..., "--project")):
    portfolio = opened(ctx)
    typer.echo(portfolio.create_draft(project, portfolio.revision))


@drafts.command("edit")
@safe
def draft_edit(ctx: typer.Context, draft_id: str, file: Path | None = typer.Option(None, "--file"), revision: int | None = typer.Option(None, "--revision")):
    portfolio = opened(ctx)
    revision = portfolio.revision if revision is None else revision
    save_edit(portfolio, portfolio.draft_document(draft_id), file, revision,
              lambda document, expected: portfolio.edit_draft(draft_id, document, expected))


@drafts.command("review")
@safe
def draft_review(ctx: typer.Context, draft_id: str, display_only: bool = typer.Option(False, "--show"),
                 approve: str | None = typer.Option(None, "--approve"), revision: int | None = typer.Option(None, "--revision")):
    portfolio = opened(ctx)
    view = portfolio.draft_review(draft_id)
    show(view)
    if display_only:
        return
    if approve is None and not typer.confirm("각 문장의 본문, 연결 주장과 공개 범위를 확인했습니까?"):
        return
    portfolio.confirm_draft(draft_id, view["revision"] if revision is None else revision, approve or view["digest"])
    typer.echo("Draft confirmed for the exact reviewed text and references.")


@app.command("review")
@safe
def review_queue(ctx: typer.Context):
    show(opened(ctx).reviews())


@app.command("refresh")
@safe
def refresh(ctx: typer.Context, source: Path | None = typer.Option(None, "--source"),
            probe_selected: bool = typer.Option(False, "--probe-selected"), legacy: bool = typer.Option(False, "--legacy")):
    portfolio = opened(ctx)
    source = source or portfolio.source_path()
    if source:
        portfolio.import_collection(read_snapshot(source, legacy=legacy or portfolio.legacy_source()), portfolio.revision, source=source)
    failures = 0
    if probe_selected:
        from acta.client import GitHubClient
        from acta.portfolio.probe import probe
        client = GitHubClient()
        selected = {p["id"] for p in portfolio.projects() if p["selected"]}
        for evidence in portfolio.evidence():
            if evidence["project_id"] in selected and evidence["kind"] != "manual":
                revision = portfolio.revision
                observation, resource = probe(evidence, client)
                portfolio.apply_probe(evidence["id"], observation, revision, resource=resource)
                failures += observation["outcome"] == "failed"
    show({"reviews": portfolio.reviews(), "probe_failures": failures})
    if failures:
        raise typer.Exit(1)


@app.command("export")
@safe
def export(ctx: typer.Context, draft_id: str, output: Path = typer.Option(Path("./portfolio_exports"), "--output"),
           audience: str = typer.Option("public", "--audience"), exclude_block: list[str] = typer.Option([], "--exclude-block")):
    if audience != "public":
        raise ValueError("This release supports public local exports only")
    portfolio = opened(ctx)
    excluded = tuple(exclude_block)
    plan = portfolio.prepare_export(draft_id, excluded=excluded)
    typer.echo(str(portfolio.publish_export(plan, output, excluded=excluded)))


@app.command("backup")
@safe
def backup(ctx: typer.Context, output: Path = typer.Option(..., "--output")):
    opened(ctx).store.backup(output)
    typer.echo(str(output))


@drafts.command("list")
@safe
def draft_list(ctx: typer.Context, project: str | None = typer.Option(None, "--project")):
    show(opened(ctx).drafts(project))


@claims.command("history")
@safe
def claim_history(ctx: typer.Context, claim_id: str):
    show(opened(ctx).history("claims", claim_id))


@drafts.command("history")
@safe
def draft_history(ctx: typer.Context, draft_id: str):
    show(opened(ctx).history("drafts", draft_id))
