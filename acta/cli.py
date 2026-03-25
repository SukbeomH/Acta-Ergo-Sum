"""Acta Ergo Sum — CLI 엔트리포인트."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer

from acta.client import GitHubClient
from acta.extractors import (
    extract_commits,
    extract_contributed_repos,
    extract_issues,
    extract_organizations,
    extract_projects,
    extract_pull_requests,
    extract_readmes,
    extract_repositories,
    extract_reviews,
    extract_stars,
)
from acta.writers import generate_metadata, generate_timeline

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


def _create_directories(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        (base / sub).mkdir(exist_ok=True)
    typer.echo(f"✓  Output directories ready under: {base.resolve()}")


@app.command()
def run(
    days: int = typer.Option(365, "--days", "-d", help="Number of past days to include."),
    output: str = typer.Option("./acta_data", "--output", "-o", help="Output base directory."),
    skip_readmes: bool = typer.Option(False, "--skip-readmes", help="Skip README archival (faster)."),
    skip_commits: bool = typer.Option(False, "--skip-commits", help="Skip commit extraction."),
    skip_prs: bool = typer.Option(False, "--skip-prs", help="Skip pull request extraction."),
    skip_stars: bool = typer.Option(False, "--skip-stars", help="Skip star extraction."),
    skip_contributed: bool = typer.Option(False, "--skip-contributed", help="Skip contributed repos extraction."),
    skip_issues: bool = typer.Option(False, "--skip-issues", help="Skip issue extraction."),
    skip_reviews: bool = typer.Option(False, "--skip-reviews", help="Skip code review extraction."),
) -> None:
    """Collect GitHub activity and write to a markdown knowledge base."""
    base = Path(output)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    typer.echo(f"🚀  Acta Ergo Sum — collecting {days} days of activity")
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

    generate_metadata(base, login, days, repos, commits, prs, stars, projects, orgs, SUBDIRS, issues=issues, reviews=reviews)
    generate_timeline(base, commits, prs, stars, issues=issues, reviews=reviews)

    typer.echo("\n✅  Done! Knowledge base is ready.")


@app.command()
def whoami() -> None:
    """Print the currently authenticated GitHub user."""
    client = GitHubClient()
    login = client.get_authenticated_user()
    typer.echo(f"Authenticated as: {login}")
