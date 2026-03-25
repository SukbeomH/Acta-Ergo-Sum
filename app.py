"""
Acta Ergo Sum — GitHub Activity Data Extractor
I act, therefore I am.

Usage:
    python app.py run --days 365
    python app.py run --days 90 --output ./my_data
"""

from __future__ import annotations

import base64
import csv
import json
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import typer

app = typer.Typer(
    name="acta",
    help="Acta Ergo Sum — Collect your GitHub activity into a markdown knowledge base.",
    add_completion=False,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SUBDIRS = [
    "repositories",
    "commits",
    "pull_requests",
    "readmes",
    "stars",
    "projects",
    "organizations",
]

_RATE_LIMIT_DELAY = 0.3  # seconds between API calls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_gh(args: list[str], *, retries: int = 3, delay: float = 5.0) -> Any:
    """Run a `gh` CLI command and return parsed JSON output."""
    cmd = ["gh"] + args
    for attempt in range(retries):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            if result.stdout.strip():
                return json.loads(result.stdout)
            return {}
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            if "rate limit" in stderr.lower() and attempt < retries - 1:
                typer.echo(
                    f"  ⚠  Rate limit hit. Waiting {delay}s before retry…", err=True
                )
                time.sleep(delay)
                delay *= 2
            else:
                typer.echo(f"  ✗  gh command failed: {' '.join(cmd)}", err=True)
                typer.echo(f"     {stderr.strip()}", err=True)
                return None
        except json.JSONDecodeError:
            typer.echo(
                f"  ✗  Could not parse JSON from: {' '.join(cmd)}", err=True
            )
            return None


def _run_gh_graphql(query: str, variables: dict[str, Any]) -> Any:
    """Execute a GraphQL query via `gh api graphql`."""
    cmd = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={query}",
    ]
    for key, value in variables.items():
        if isinstance(value, bool):
            cmd += ["-F", f"{key}={str(value).lower()}"]
        elif isinstance(value, int):
            cmd += ["-F", f"{key}={value}"]
        else:
            cmd += ["-f", f"{key}={value}"]

    for attempt in range(3):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            data = json.loads(result.stdout)
            if "errors" in data:
                typer.echo(
                    f"  ✗  GraphQL errors: {data['errors']}", err=True
                )
                return None
            return data.get("data")
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            if "rate limit" in stderr.lower() and attempt < 2:
                typer.echo("  ⚠  Rate limit hit on GraphQL. Waiting…", err=True)
                time.sleep(10 * (attempt + 1))
            else:
                typer.echo(f"  ✗  GraphQL call failed: {stderr.strip()}", err=True)
                return None
        except json.JSONDecodeError:
            return None


def _write_md(path: Path, frontmatter: dict[str, Any], body: str = "") -> None:
    """Write a markdown file with YAML frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, str) and ("\n" in value or '"' in value):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}: "{escaped}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    if body:
        lines.append("")
        lines.append(body)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _get_authenticated_user() -> str:
    """Return the login of the currently authenticated GitHub user."""
    data = _run_gh(["api", "/user"])
    if not data or "login" not in data:
        typer.echo("✗  Could not retrieve authenticated user. Is `gh auth login` done?", err=True)
        raise typer.Exit(code=1)
    return data["login"]


def _iso_to_dt(iso: str) -> datetime:
    """Parse an ISO 8601 string to a timezone-aware datetime."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------------------


def _create_directories(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    for sub in _SUBDIRS:
        (base / sub).mkdir(exist_ok=True)
    typer.echo(f"✓  Output directories ready under: {base.resolve()}")


# ---------------------------------------------------------------------------
# 1. Repositories
# ---------------------------------------------------------------------------

_REPO_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(
      first: 100
      after: $after
      orderBy: {field: UPDATED_AT, direction: DESC}
      ownerAffiliations: [OWNER]
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        description
        url
        createdAt
        updatedAt
        pushedAt
        primaryLanguage { name }
        repositoryTopics(first: 20) { nodes { topic { name } } }
        isFork
        isPrivate
        stargazerCount
        forkCount
        defaultBranchRef { name }
      }
    }
  }
}
"""


def extract_repositories(base: Path, login: str, since: datetime) -> list[dict]:
    """Fetch all owned repositories and write one markdown file per repo."""
    typer.echo("→  Extracting repositories…")
    cursor: Optional[str] = None
    repos: list[dict] = []
    page = 0

    while True:
        variables: dict[str, Any] = {"login": login}
        if cursor:
            variables["after"] = cursor

        data = _run_gh_graphql(_REPO_QUERY, variables)
        if not data:
            break

        page_data = data["user"]["repositories"]
        nodes = page_data["nodes"]
        repos.extend(nodes)
        page += 1
        typer.echo(f"   page {page}: {len(nodes)} repos")

        if not page_data["pageInfo"]["hasNextPage"]:
            break
        cursor = page_data["pageInfo"]["endCursor"]
        time.sleep(_RATE_LIMIT_DELAY)

    written = 0
    for repo in repos:
        topics = [n["topic"]["name"] for n in repo.get("repositoryTopics", {}).get("nodes", [])]
        lang = repo.get("primaryLanguage") or {}
        branch = repo.get("defaultBranchRef") or {}

        frontmatter: dict[str, Any] = {
            "name": repo["name"],
            "url": repo["url"],
            "created_at": repo["createdAt"],
            "updated_at": repo["updatedAt"],
            "pushed_at": repo.get("pushedAt", ""),
            "language": lang.get("name", ""),
            "topics": topics,
            "is_fork": repo["isFork"],
            "is_private": repo["isPrivate"],
            "stars": repo["stargazerCount"],
            "forks": repo["forkCount"],
            "default_branch": branch.get("name", "main"),
        }
        desc = repo.get("description") or ""
        body = f"## {repo['name']}\n\n{desc}" if desc else f"## {repo['name']}"
        _write_md(base / "repositories" / f"{repo['name']}.md", frontmatter, body)
        written += 1

    typer.echo(f"✓  Repositories: {written} files written")
    return repos


# ---------------------------------------------------------------------------
# 2. Commits
# ---------------------------------------------------------------------------

_COMMIT_QUERY = """
query($owner: String!, $name: String!, $since: GitTimestamp!, $after: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, after: $after, since: $since) {
            pageInfo { hasNextPage endCursor }
            nodes {
              oid
              message
              committedDate
              author { name email user { login } }
            }
          }
        }
      }
    }
  }
}
"""


def extract_commits(
    base: Path, login: str, repos: list[dict], since: datetime
) -> list[dict]:
    """Fetch commits authored by `login` across all owned repos, grouped by YYYY-MM."""
    typer.echo("→  Extracting commits…")
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    # month -> list of commit dicts
    by_month: dict[str, list[dict]] = defaultdict(list)
    all_commits: list[dict] = []

    for repo in repos:
        repo_name = repo["name"]
        if repo.get("isFork"):
            continue  # skip forks to avoid duplicate counting

        cursor: Optional[str] = None
        while True:
            variables: dict[str, Any] = {
                "owner": login,
                "name": repo_name,
                "since": since_iso,
            }
            if cursor:
                variables["after"] = cursor

            data = _run_gh_graphql(_COMMIT_QUERY, variables)
            if not data:
                break

            default_ref = data.get("repository", {}).get("defaultBranchRef")
            if not default_ref:
                break
            history = default_ref["target"]["history"]
            nodes = history["nodes"]

            for node in nodes:
                author = node.get("author") or {}
                user = author.get("user") or {}
                if user.get("login", "").lower() != login.lower():
                    continue
                month = node["committedDate"][:7]
                entry = {
                    "repo": repo_name,
                    "sha": node["oid"][:7],
                    "message": node["message"].split("\n")[0],  # commit subject line (before first blank line)
                    "date": node["committedDate"],
                }
                by_month[month].append(entry)
                all_commits.append(entry)

            if not history["pageInfo"]["hasNextPage"]:
                break
            cursor = history["pageInfo"]["endCursor"]
            time.sleep(_RATE_LIMIT_DELAY)

        time.sleep(_RATE_LIMIT_DELAY)

    # Write one file per month
    for month, entries in sorted(by_month.items()):
        frontmatter: dict[str, Any] = {
            "period": month,
            "category": "commits",
            "total": len(entries),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        lines = [f"## Commits — {month}", ""]
        for e in sorted(entries, key=lambda x: x["date"]):
            lines.append(f"- `{e['date'][:10]}` **{e['repo']}** `{e['sha']}` {e['message']}")
        _write_md(base / "commits" / f"{month}.md", frontmatter, "\n".join(lines))

    typer.echo(f"✓  Commits: {len(all_commits)} commits across {len(by_month)} months")
    return all_commits


# ---------------------------------------------------------------------------
# 3. Pull Requests & Reviews
# ---------------------------------------------------------------------------

_PR_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    pullRequests(
      first: 50
      after: $after
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        state
        createdAt
        mergedAt
        closedAt
        url
        body
        repository { nameWithOwner }
        reviews(first: 20) {
          nodes {
            state
            body
            createdAt
            author { login }
          }
        }
        comments(first: 10) {
          nodes {
            body
            createdAt
            author { login }
          }
        }
      }
    }
  }
}
"""


def extract_pull_requests(
    base: Path, login: str, since: datetime
) -> list[dict]:
    """Fetch all PRs authored by the user and write one markdown file per PR."""
    typer.echo("→  Extracting pull requests…")
    cursor: Optional[str] = None
    prs: list[dict] = []
    page = 0

    while True:
        variables: dict[str, Any] = {"login": login}
        if cursor:
            variables["after"] = cursor

        data = _run_gh_graphql(_PR_QUERY, variables)
        if not data:
            break

        page_data = data["user"]["pullRequests"]
        nodes = page_data["nodes"]

        # Stop if all PRs on this page are older than `since`
        reached_cutoff = False
        for node in nodes:
            created = _iso_to_dt(node["createdAt"])
            if created < since:
                reached_cutoff = True
                break
            prs.append(node)

        page += 1
        typer.echo(f"   page {page}: {len(prs)} PRs so far")

        if reached_cutoff or not page_data["pageInfo"]["hasNextPage"]:
            break
        cursor = page_data["pageInfo"]["endCursor"]
        time.sleep(_RATE_LIMIT_DELAY)

    for pr in prs:
        repo_name = pr["repository"]["nameWithOwner"].replace("/", "_")
        state = pr["state"]
        merged = "true" if pr.get("mergedAt") else "false"

        frontmatter: dict[str, Any] = {
            "pr_number": pr["number"],
            "title": pr["title"],
            "repository": pr["repository"]["nameWithOwner"],
            "state": state,
            "merged": merged,
            "created_at": pr["createdAt"],
            "merged_at": pr.get("mergedAt", ""),
            "closed_at": pr.get("closedAt", ""),
            "url": pr["url"],
            "category": "pull_request",
        }

        # Build body
        body_lines = [
            f"## PR #{pr['number']}: {pr['title']}",
            "",
            f"**Repository:** {pr['repository']['nameWithOwner']}  ",
            f"**State:** {state}  ",
            f"**Created:** {pr['createdAt'][:10]}",
        ]
        if pr.get("mergedAt"):
            body_lines.append(f"**Merged:** {pr['mergedAt'][:10]}")

        if pr.get("body", "").strip():
            body_lines += ["", "### Description", "", pr["body"].strip()]

        reviews = pr.get("reviews", {}).get("nodes", [])
        if reviews:
            body_lines += ["", "### Reviews"]
            for rev in reviews:
                author = (rev.get("author") or {}).get("login", "unknown")
                body_lines.append(
                    f"- **{author}** ({rev['state']}) on {rev['createdAt'][:10]}"
                )
                if rev.get("body", "").strip():
                    body_lines.append(f"  > {rev['body'].strip()[:200]}")

        filename = f"{repo_name}_pr{pr['number']}.md"
        _write_md(
            base / "pull_requests" / filename,
            frontmatter,
            "\n".join(body_lines),
        )

    typer.echo(f"✓  Pull Requests: {len(prs)} files written")
    return prs


# ---------------------------------------------------------------------------
# 4. READMEs
# ---------------------------------------------------------------------------


def extract_readmes(base: Path, login: str, repos: list[dict]) -> int:
    """Fetch and archive README.md for each owned repository."""
    typer.echo("→  Archiving READMEs…")
    written = 0

    for repo in repos:
        repo_name = repo["name"]
        data = _run_gh(
            ["api", f"/repos/{login}/{repo_name}/readme", "--header", "Accept: application/vnd.github.raw+json"]
        )
        if data is None:
            # Try raw content via REST
            try:
                result = subprocess.run(
                    ["gh", "api", f"/repos/{login}/{repo_name}/readme"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                )
                meta = json.loads(result.stdout)
                content = base64.b64decode(meta.get("content", "")).decode("utf-8", errors="replace")
            except Exception:
                time.sleep(_RATE_LIMIT_DELAY)
                continue
        else:
            # data came back as a dict (base64 encoded content)
            if isinstance(data, dict) and "content" in data:
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            else:
                content = ""

        if not content.strip():
            time.sleep(_RATE_LIMIT_DELAY)
            continue

        frontmatter: dict[str, Any] = {
            "repo": repo_name,
            "url": repo.get("url", ""),
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "category": "readme",
        }
        out_path = base / "readmes" / f"{repo_name}_readme.md"
        _write_md(out_path, frontmatter, content)
        written += 1
        time.sleep(_RATE_LIMIT_DELAY)

    typer.echo(f"✓  READMEs: {written} files archived")
    return written


# ---------------------------------------------------------------------------
# 5. Stars
# ---------------------------------------------------------------------------


def extract_stars(base: Path, login: str, since: datetime) -> list[dict]:
    """Fetch starred repositories including the star timestamp, grouped by YYYY-MM."""
    typer.echo("→  Extracting starred repositories…")
    page = 1
    per_page = 100
    by_month: dict[str, list[dict]] = defaultdict(list)
    all_stars: list[dict] = []

    while True:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "api",
                    f"/users/{login}/starred",
                    "--header",
                    "Accept: application/vnd.github.star+json",
                    "-F",
                    f"per_page={per_page}",
                    "-F",
                    f"page={page}",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            items = json.loads(result.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            break

        if not items:
            break

        reached_cutoff = False
        for item in items:
            starred_at_str = item.get("starred_at", "")
            if not starred_at_str:
                # Skip entries without a valid star timestamp to avoid misleading data
                continue
            starred_at = _iso_to_dt(starred_at_str)

            if starred_at < since:
                reached_cutoff = True
                break

            starred_repo = item.get("repo", {})
            topics = starred_repo.get("topics", [])
            entry = {
                "starred_at": starred_at_str,
                "name": starred_repo.get("full_name", ""),
                "description": (starred_repo.get("description") or "").strip(),
                "url": starred_repo.get("html_url", ""),
                "language": starred_repo.get("language") or "",
                "topics": topics,
                "stars": starred_repo.get("stargazers_count", 0),
            }
            month = entry["starred_at"][:7]
            by_month[month].append(entry)
            all_stars.append(entry)

        if reached_cutoff or len(items) < per_page:
            break
        page += 1
        time.sleep(_RATE_LIMIT_DELAY)

    for month, entries in sorted(by_month.items()):
        frontmatter: dict[str, Any] = {
            "period": month,
            "category": "stars",
            "total": len(entries),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        lines = [f"## Stars — {month}", ""]
        for e in sorted(entries, key=lambda x: x["starred_at"], reverse=True):
            topic_str = ", ".join(e["topics"]) if e["topics"] else ""
            lines.append(f"### [{e['name']}]({e['url']})")
            lines.append(f"- **Starred:** {e['starred_at'][:10]}")
            lines.append(f"- **Language:** {e['language']}")
            if e["description"]:
                lines.append(f"- **Description:** {e['description']}")
            if topic_str:
                lines.append(f"- **Topics:** {topic_str}")
            lines.append("")
        _write_md(base / "stars" / f"{month}.md", frontmatter, "\n".join(lines))

    typer.echo(f"✓  Stars: {len(all_stars)} starred repos across {len(by_month)} months")
    return all_stars


# ---------------------------------------------------------------------------
# 6. Projects
# ---------------------------------------------------------------------------


def extract_projects(base: Path, login: str) -> list[dict]:
    """Fetch GitHub Projects (v2) for the user."""
    typer.echo("→  Extracting GitHub Projects…")

    query = """
    query($login: String!, $after: String) {
      user(login: $login) {
        projectsV2(first: 50, after: $after) {
          pageInfo { hasNextPage endCursor }
          nodes {
            number
            title
            shortDescription
            url
            createdAt
            updatedAt
            closed
            public
          }
        }
      }
    }
    """

    cursor: Optional[str] = None
    projects: list[dict] = []

    while True:
        variables: dict[str, Any] = {"login": login}
        if cursor:
            variables["after"] = cursor

        data = _run_gh_graphql(query, variables)
        if not data:
            break

        page_data = data["user"]["projectsV2"]
        projects.extend(page_data["nodes"])

        if not page_data["pageInfo"]["hasNextPage"]:
            break
        cursor = page_data["pageInfo"]["endCursor"]
        time.sleep(_RATE_LIMIT_DELAY)

    for proj in projects:
        frontmatter: dict[str, Any] = {
            "project_number": proj["number"],
            "title": proj["title"],
            "url": proj["url"],
            "created_at": proj["createdAt"],
            "updated_at": proj["updatedAt"],
            "closed": proj["closed"],
            "public": proj["public"],
            "category": "project",
        }
        desc = proj.get("shortDescription") or ""
        body = f"## {proj['title']}\n\n{desc}" if desc else f"## {proj['title']}"
        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in proj["title"])
        _write_md(
            base / "projects" / f"project_{proj['number']}_{safe_title}.md",
            frontmatter,
            body,
        )

    typer.echo(f"✓  Projects: {len(projects)} files written")
    return projects


# ---------------------------------------------------------------------------
# 7. Organizations
# ---------------------------------------------------------------------------


def extract_organizations(base: Path, login: str) -> list[dict]:
    """Fetch organizations the user belongs to."""
    typer.echo("→  Extracting organizations…")
    data = _run_gh(["api", "/user/orgs", "-F", "per_page=100"])
    if not isinstance(data, list):
        data = []

    for org in data:
        frontmatter: dict[str, Any] = {
            "login": org.get("login", ""),
            "description": (org.get("description") or "").strip(),
            "url": org.get("url", ""),
            "repos_url": org.get("repos_url", ""),
            "category": "organization",
        }
        body = f"## {org.get('login', '')}\n\n{org.get('description', '') or ''}"
        _write_md(
            base / "organizations" / f"{org.get('login', 'unknown')}.md",
            frontmatter,
            body,
        )

    typer.echo(f"✓  Organizations: {len(data)} files written")
    return data


# ---------------------------------------------------------------------------
# 8. Metadata & Timeline
# ---------------------------------------------------------------------------


def generate_metadata(
    base: Path,
    login: str,
    days: int,
    repos: list[dict],
    commits: list[dict],
    prs: list[dict],
    stars: list[dict],
    projects: list[dict],
    orgs: list[dict],
) -> None:
    """Write metadata.json — an LLM-friendly index of everything extracted."""
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_user": login,
        "period_days": days,
        "summary": {
            "repositories": len(repos),
            "commits": len(commits),
            "pull_requests": len(prs),
            "stars": len(stars),
            "projects": len(projects),
            "organizations": len(orgs),
        },
        "directories": {d: f"{d}/" for d in _SUBDIRS},
        "top_languages": _top_languages(repos),
        "top_starred_languages": _top_languages_from_stars(stars),
    }
    (base / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    typer.echo("✓  metadata.json written")


def _top_languages(repos: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for repo in repos:
        lang = (repo.get("primaryLanguage") or {}).get("name")
        if lang:
            counts[lang] += 1
    return dict(sorted(counts.items(), key=lambda x: -x[1])[:10])


def _top_languages_from_stars(stars: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for star in stars:
        lang = star.get("language")
        if lang:
            counts[lang] += 1
    return dict(sorted(counts.items(), key=lambda x: -x[1])[:10])


def generate_timeline(
    base: Path,
    commits: list[dict],
    prs: list[dict],
    stars: list[dict],
) -> None:
    """Write timeline.csv — a chronological record of all activity."""
    rows: list[dict[str, str]] = []

    for c in commits:
        rows.append(
            {
                "date": c["date"][:10],
                "category": "Commit",
                "repository": c["repo"],
                "action": c["message"][:120],
            }
        )

    for pr in prs:
        rows.append(
            {
                "date": pr["createdAt"][:10],
                "category": "PR",
                "repository": pr["repository"]["nameWithOwner"],
                "action": f"[{pr['state']}] {pr['title'][:120]}",
            }
        )

    for s in stars:
        rows.append(
            {
                "date": s["starred_at"][:10],
                "category": "Star",
                "repository": s["name"],
                "action": s["description"][:120] if s["description"] else s["name"],
            }
        )

    rows.sort(key=lambda r: r["date"], reverse=True)

    out = base / "timeline.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["date", "category", "repository", "action"])
        writer.writeheader()
        writer.writerows(rows)

    typer.echo(f"✓  timeline.csv written ({len(rows)} rows)")


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------


@app.command()
def run(
    days: int = typer.Option(365, "--days", "-d", help="Number of past days to include."),
    output: str = typer.Option("./acta_data", "--output", "-o", help="Output base directory."),
    skip_readmes: bool = typer.Option(False, "--skip-readmes", help="Skip README archival (faster)."),
    skip_commits: bool = typer.Option(False, "--skip-commits", help="Skip commit extraction."),
    skip_prs: bool = typer.Option(False, "--skip-prs", help="Skip pull request extraction."),
    skip_stars: bool = typer.Option(False, "--skip-stars", help="Skip star extraction."),
) -> None:
    """Collect GitHub activity and write to a markdown knowledge base."""
    base = Path(output)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    typer.echo(f"🚀  Acta Ergo Sum — collecting {days} days of activity")
    typer.echo(f"    Output: {base.resolve()}")
    typer.echo(f"    Since:  {since.strftime('%Y-%m-%d')}\n")

    # Pre-flight: check `gh` is available
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        typer.echo("✗  `gh` CLI not found. Install from https://cli.github.com/", err=True)
        raise typer.Exit(code=1)

    login = _get_authenticated_user()
    typer.echo(f"    User:   {login}\n")

    _create_directories(base)
    typer.echo("")

    # --- Extract data ---
    repos = extract_repositories(base, login, since)
    typer.echo("")

    commits: list[dict] = []
    if not skip_commits:
        commits = extract_commits(base, login, repos, since)
        typer.echo("")

    prs: list[dict] = []
    if not skip_prs:
        prs = extract_pull_requests(base, login, since)
        typer.echo("")

    if not skip_readmes:
        extract_readmes(base, login, repos)
        typer.echo("")

    stars: list[dict] = []
    if not skip_stars:
        stars = extract_stars(base, login, since)
        typer.echo("")

    projects = extract_projects(base, login)
    typer.echo("")

    orgs = extract_organizations(base, login)
    typer.echo("")

    # --- Summaries ---
    generate_metadata(base, login, days, repos, commits, prs, stars, projects, orgs)
    generate_timeline(base, commits, prs, stars)

    typer.echo("\n✅  Done! Knowledge base is ready.")


@app.command()
def whoami() -> None:
    """Print the currently authenticated GitHub user."""
    login = _get_authenticated_user()
    typer.echo(f"Authenticated as: {login}")


if __name__ == "__main__":
    app()
