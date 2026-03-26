"""Acta Ergo Sum — CLI 엔트리포인트."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer

from acta.client import GitHubClient
from acta.extractors import (
    extract_commits,
    extract_contributed_repos,
    extract_contribution_calendar,
    extract_issues,
    extract_organizations,
    extract_pinned_repos,
    extract_profile,
    extract_projects,
    extract_pull_requests,
    extract_readmes,
    extract_repositories,
    extract_reviews,
    extract_stars,
)
from acta.writers import generate_metadata, generate_summary, generate_timeline

app = typer.Typer(
    name="acta",
    help="Acta Ergo Sum — Collect your GitHub activity into a markdown knowledge base.",
    add_completion=False,
)

SUBDIRS = [
    "repositories",
    "commits",
    "pull_requests",
    "issues",
    "reviews",
    "readmes",
    "stars",
    "projects",
    "organizations",
]


def _read_last_run(meta_path: Path, fallback_days: int) -> datetime:
    """metadata.json에서 generated_at을 읽어 since를 결정한다."""
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            generated_at = meta.get("generated_at", "")
            if generated_at:
                since = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                typer.echo(f"    Last run: {since.strftime('%Y-%m-%d %H:%M')}")
                return since
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
    typer.echo(f"    No previous run found. Using --days {fallback_days} as fallback.")
    return datetime.now(timezone.utc) - timedelta(days=fallback_days)


def _create_directories(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        (base / sub).mkdir(exist_ok=True)
    typer.echo(f"✓  Output directories ready under: {base.resolve()}")


@app.command()
def run(
    days: int = typer.Option(365, "--days", "-d", help="Number of past days to include."),
    months: int = typer.Option(0, "--months", "-m", help="Number of past months (overrides --days if set)."),
    years: int = typer.Option(0, "--years", "-y", help="Number of past years (overrides --days/--months if set)."),
    output: str = typer.Option("./acta_data", "--output", "-o", help="Output base directory."),
    skip_readmes: bool = typer.Option(False, "--skip-readmes", help="Skip README archival (faster)."),
    skip_commits: bool = typer.Option(False, "--skip-commits", help="Skip commit extraction."),
    skip_prs: bool = typer.Option(False, "--skip-prs", help="Skip pull request extraction."),
    skip_stars: bool = typer.Option(False, "--skip-stars", help="Skip star extraction."),
    skip_contributed: bool = typer.Option(False, "--skip-contributed", help="Skip contributed repos extraction."),
    skip_issues: bool = typer.Option(False, "--skip-issues", help="Skip issue extraction."),
    skip_reviews: bool = typer.Option(False, "--skip-reviews", help="Skip code review extraction."),
    since_last_run: bool = typer.Option(False, "--since-last-run", help="Only collect data since the last run."),
) -> None:
    """Collect GitHub activity and write to a markdown knowledge base."""
    base = Path(output)

    # 기간 우선순위: --since-last-run > --years > --months > --days
    if since_last_run:
        total_days = years * 365 + months * 30 + days if (years or months) else days
        meta_path = base / "metadata.json"
        since = _read_last_run(meta_path, total_days)
    elif years:
        since = datetime.now(timezone.utc) - timedelta(days=years * 365)
    elif months:
        since = datetime.now(timezone.utc) - timedelta(days=months * 30)
    else:
        since = datetime.now(timezone.utc) - timedelta(days=days)

    typer.echo(f"🚀  Acta Ergo Sum — collecting activity")
    typer.echo(f"    Output: {base.resolve()}")
    typer.echo(f"    Since:  {since.strftime('%Y-%m-%d')}\n")

    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        typer.echo("✗  `gh` CLI not found. Install from https://cli.github.com/", err=True)
        raise typer.Exit(code=1)

    client = GitHubClient()
    login = client.get_authenticated_user()
    typer.echo(f"    User:   {login}\n")

    _create_directories(base)
    typer.echo("")

    profile = extract_profile(client, base, login)
    typer.echo("")

    pinned = extract_pinned_repos(client, base, login)
    typer.echo("")

    calendar = extract_contribution_calendar(client, base, login, since)
    typer.echo("")

    repos = extract_repositories(client, base, login, since)
    typer.echo("")

    contributed: list[dict] = []
    if not skip_contributed:
        owner_names = {r["name"] for r in repos}
        contributed = extract_contributed_repos(client, base, login, since, exclude_names=owner_names)
        repos = repos + contributed
        typer.echo("")

    commits: list[dict] = []
    if not skip_commits:
        commits = extract_commits(client, base, login, repos, since)
        typer.echo("")

    prs: list[dict] = []
    if not skip_prs:
        prs = extract_pull_requests(client, base, login, since)
        typer.echo("")

    issues: list[dict] = []
    if not skip_issues:
        issues = extract_issues(client, base, login, since)
        typer.echo("")

    reviews: list[dict] = []
    if not skip_reviews:
        reviews = extract_reviews(client, base, login, since)
        typer.echo("")

    if not skip_readmes:
        extract_readmes(client, base, login, repos)
        typer.echo("")

    stars: list[dict] = []
    if not skip_stars:
        stars = extract_stars(client, base, login, since)
        typer.echo("")

    projects = extract_projects(client, base, login)
    typer.echo("")

    orgs = extract_organizations(client, base, login)
    typer.echo("")

    generate_metadata(base, login, days, repos, commits, prs, stars, projects, orgs, SUBDIRS, issues=issues, reviews=reviews, pinned=pinned, calendar=calendar)
    generate_timeline(base, commits, prs, stars, issues=issues, reviews=reviews)
    generate_summary(base, login, days, repos, commits, prs, issues, reviews, stars, projects, orgs, pinned=pinned, calendar=calendar)
    typer.echo("✓  SUMMARY.md written")

    typer.echo("\n✅  Done! Knowledge base is ready.")


@app.command()
def analyze(
    template: str = typer.Option(..., "--template", "-t", help="Template name (e.g. profile, weekly, resume)."),
    input_dir: str = typer.Option("./acta_data", "--input", "-i", help="Input data directory."),
    call_api: bool = typer.Option(False, "--call-api", help="Call Claude API to generate result."),
    template_dir: str = typer.Option("./templates", "--template-dir", help="Templates directory."),
) -> None:
    """Analyze collected data using LLM prompt templates."""
    from acta.analyzer import build_prompt, call_api as api_call, list_templates, load_template

    data_dir = Path(input_dir)
    tmpl_dir = Path(template_dir)
    tmpl_path = tmpl_dir / f"{template}.md"

    if not tmpl_path.exists():
        available = list_templates(tmpl_dir)
        typer.echo(f"✗  Template '{template}' not found.", err=True)
        if available:
            typer.echo(f"   Available: {', '.join(available)}", err=True)
        raise typer.Exit(code=1)

    if not data_dir.exists():
        typer.echo(f"✗  Data directory '{data_dir}' not found. Run `acta run` first.", err=True)
        raise typer.Exit(code=1)

    meta, body = load_template(tmpl_path)
    context_files = meta.get("context", [])
    max_tokens = meta.get("max_tokens", 4096)

    typer.echo(f"📝  Template: {meta.get('name', template)}")
    typer.echo(f"    Description: {meta.get('description', '')}")
    typer.echo(f"    Context files: {', '.join(context_files)}")

    prompt = build_prompt(body, context_files, data_dir)

    # Save prompt
    analysis_dir = data_dir / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    prompt_path = analysis_dir / f"{template}.prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    typer.echo(f"✓  Prompt saved: {prompt_path}")

    if call_api:
        typer.echo("🤖  Calling Claude API…")
        try:
            result = api_call(prompt, max_tokens=max_tokens)
            result_path = analysis_dir / f"{template}.result.md"
            result_path.write_text(result, encoding="utf-8")
            typer.echo(f"✓  Result saved: {result_path}")
        except RuntimeError as e:
            typer.echo(f"✗  {e}", err=True)
            raise typer.Exit(code=1)
    else:
        typer.echo(f"\n💡  To generate with Claude API, add --call-api")


@app.command()
def deep(
    repo: str = typer.Argument(..., help="Repository to analyze (owner/repo)."),
    output: str = typer.Option("./deep_analysis", "--output", "-o", help="Output directory."),
    stdout: bool = typer.Option(False, "--stdout", help="Print all sections to stdout instead of files."),
    include_me: bool = typer.Option(False, "--include-me", help="Include my contribution analysis."),
) -> None:
    """Deep-analyze a GitHub repository for LLM context."""
    from acta.deep.collector import DeepCollector
    from acta.deep.detector import detect_key_files
    from acta.deep.renderer import render_all_sections

    parts = repo.strip().split("/")
    if len(parts) != 2:
        typer.echo("✗  Format: owner/repo", err=True)
        raise typer.Exit(code=1)
    owner, name = parts

    typer.echo(f"🔍  Deep analyzing {repo}…")

    client = GitHubClient()
    collector = DeepCollector(client, owner, name)

    # 데이터 수집
    typer.echo("\n📦  Collecting data…")
    overview = collector.fetch_overview()
    if not overview:
        typer.echo("✗  Could not fetch repository data.", err=True)
        raise typer.Exit(code=1)

    readme = collector.fetch_readme()
    tree_paths = collector.fetch_tree()
    languages = collector.fetch_languages()

    # 핵심 파일 내용 수집
    typer.echo("  → key files…")
    key_files = detect_key_files(tree_paths)
    key_file_contents: dict[str, str] = {}
    for _cat, paths in key_files.items():
        for path in paths[:3]:
            content = collector.fetch_file_content(path)
            if content:
                key_file_contents[path] = content

    deps = collector.fetch_dependencies()
    releases = collector.fetch_releases()

    # CHANGELOG
    changelog = ""
    for fname in ["CHANGELOG.md", "CHANGES.md", "HISTORY.md"]:
        if fname in tree_paths:
            changelog = collector.fetch_file_content(fname)
            break

    commits = collector.fetch_recent_commits()
    health = collector.fetch_community_health()
    labels = collector.fetch_issue_labels()

    # 내 기여 (선택)
    my_stats = None
    login = ""
    if include_me:
        login = client.get_authenticated_user()
        my_stats = collector.fetch_my_contributions(login)

    # 렌더링
    typer.echo("\n📝  Rendering…")
    base = Path(output) / name
    base.mkdir(parents=True, exist_ok=True)

    sections = render_all_sections(
        base=base,
        overview=overview,
        readme=readme,
        tree_paths=tree_paths,
        languages=languages,
        key_file_contents=key_file_contents,
        dependencies=deps,
        releases=releases,
        changelog=changelog,
        recent_commits=commits,
        health=health,
        labels=labels,
        my_stats=my_stats,
        login=login,
    )

    if stdout:
        for section_name, body in sections.items():
            typer.echo(f"\n{'=' * 60}")
            typer.echo(body)
    else:
        typer.echo(f"\n✅  Deep analysis written to: {base.resolve()}")
        for section_name in sections:
            typer.echo(f"   - {section_name}.md")


@app.command()
def mcp() -> None:
    """Start the MCP server for LLM agent integration."""
    try:
        from acta.mcp_server import run_server
    except ImportError:
        typer.echo("✗  MCP dependencies not installed. Run: uv add 'mcp[cli]'", err=True)
        raise typer.Exit(code=1)
    typer.echo("🚀  Starting Acta MCP server…")
    run_server()


@app.command()
def whoami() -> None:
    """Print the currently authenticated GitHub user."""
    client = GitHubClient()
    login = client.get_authenticated_user()
    typer.echo(f"Authenticated as: {login}")
