"""GitHub 데이터 추출 함수들 — GitHubClient를 주입받는다."""

from __future__ import annotations

import base64
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import typer

from acta.client import GitHubClient
from acta.writers import write_md

# ---------------------------------------------------------------------------
# GraphQL Queries
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
              additions
              deletions
              author { name email user { login } }
            }
          }
        }
      }
    }
  }
}
"""

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_to_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _fetch_language_breakdown(client: GitHubClient, owner: str, repo_name: str) -> list[str]:
    """REST API로 레포의 언어 비율을 가져온다. 퍼센트 문자열 리스트 반환."""
    data = client.rest(f"/repos/{owner}/{repo_name}/languages")
    if not isinstance(data, dict) or not data:
        return []
    total = sum(data.values())
    if total == 0:
        return []
    return [f"{lang}: {bytes_val / total * 100:.1f}%" for lang, bytes_val in
            sorted(data.items(), key=lambda x: -x[1])]


# ---------------------------------------------------------------------------
# 1. Repositories
# ---------------------------------------------------------------------------


def extract_repositories(
    client: GitHubClient, base: Path, login: str, since: datetime
) -> list[dict]:
    typer.echo("→  Extracting repositories…")
    cursor: Optional[str] = None
    repos: list[dict] = []
    page = 0

    while True:
        variables: dict[str, Any] = {"login": login}
        if cursor:
            variables["after"] = cursor

        data = client.graphql(_REPO_QUERY, variables)
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
        time.sleep(client.rate_limit_delay)

    written = 0
    for repo in repos:
        topics = [n["topic"]["name"] for n in repo.get("repositoryTopics", {}).get("nodes", [])]
        lang = repo.get("primaryLanguage") or {}
        branch = repo.get("defaultBranchRef") or {}
        languages = _fetch_language_breakdown(client, login, repo["name"])

        frontmatter: dict[str, Any] = {
            "name": repo["name"],
            "url": repo["url"],
            "created_at": repo["createdAt"],
            "updated_at": repo["updatedAt"],
            "pushed_at": repo.get("pushedAt", ""),
            "language": lang.get("name", ""),
            "languages": languages,
            "topics": topics,
            "is_fork": repo["isFork"],
            "is_private": repo["isPrivate"],
            "stars": repo["stargazerCount"],
            "forks": repo["forkCount"],
            "default_branch": branch.get("name", "main"),
        }
        desc = repo.get("description") or ""
        body_lines = [f"## {repo['name']}"]
        if desc:
            body_lines.append(f"\n> {desc}")
        body_lines.append("")
        body_lines.append(f"- **Language**: {lang.get('name', 'N/A')}")
        if languages:
            body_lines.append(f"- **Breakdown**: {', '.join(languages[:5])}")
        body_lines.append(f"- **Stars**: {repo['stargazerCount']} | **Forks**: {repo['forkCount']}")
        body_lines.append(f"- **Last push**: {repo.get('pushedAt', 'N/A')[:10]}")
        if topics:
            body_lines.append(f"- **Topics**: {', '.join(topics)}")
        write_md(base / "repositories" / f"{repo['name']}.md", frontmatter, "\n".join(body_lines))
        written += 1
        time.sleep(client.rate_limit_delay)

    typer.echo(f"✓  Repositories: {written} files written")
    return repos


# ---------------------------------------------------------------------------
# 1b. Contributed Repositories
# ---------------------------------------------------------------------------

_CONTRIBUTED_REPO_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(
      first: 100
      after: $after
      orderBy: {field: UPDATED_AT, direction: DESC}
      ownerAffiliations: [COLLABORATOR, ORGANIZATION_MEMBER]
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


def extract_contributed_repos(
    client: GitHubClient, base: Path, login: str, since: datetime,
    exclude_names: set[str] | None = None,
) -> list[dict]:
    """COLLABORATOR/ORG_MEMBER 레포를 수집한다. exclude_names에 있는 레포는 제외."""
    typer.echo("→  Extracting contributed repositories…")
    exclude = exclude_names or set()
    cursor: Optional[str] = None
    repos: list[dict] = []
    page = 0

    while True:
        variables: dict[str, Any] = {"login": login}
        if cursor:
            variables["after"] = cursor

        data = client.graphql(_CONTRIBUTED_REPO_QUERY, variables)
        if not data:
            break

        page_data = data["user"]["repositories"]
        nodes = page_data["nodes"]
        for node in nodes:
            if node["name"] not in exclude:
                repos.append(node)
        page += 1
        typer.echo(f"   page {page}: {len(nodes)} repos ({len(repos)} after dedup)")

        if not page_data["pageInfo"]["hasNextPage"]:
            break
        cursor = page_data["pageInfo"]["endCursor"]
        time.sleep(client.rate_limit_delay)

    written = 0
    for repo in repos:
        topics = [n["topic"]["name"] for n in repo.get("repositoryTopics", {}).get("nodes", [])]
        lang = repo.get("primaryLanguage") or {}
        branch = repo.get("defaultBranchRef") or {}
        languages = _fetch_language_breakdown(client, login, repo["name"])

        frontmatter: dict[str, Any] = {
            "name": repo["name"],
            "url": repo["url"],
            "created_at": repo["createdAt"],
            "updated_at": repo["updatedAt"],
            "pushed_at": repo.get("pushedAt", ""),
            "language": lang.get("name", ""),
            "languages": languages,
            "topics": topics,
            "is_fork": repo["isFork"],
            "is_private": repo["isPrivate"],
            "stars": repo["stargazerCount"],
            "forks": repo["forkCount"],
            "default_branch": branch.get("name", "main"),
            "contributed": True,
        }
        desc = repo.get("description") or ""
        body_lines = [f"## {repo['name']}"]
        if desc:
            body_lines.append(f"\n> {desc}")
        body_lines.append("")
        body_lines.append(f"- **Language**: {lang.get('name', 'N/A')}")
        if languages:
            body_lines.append(f"- **Breakdown**: {', '.join(languages[:5])}")
        body_lines.append(f"- **Stars**: {repo['stargazerCount']} | **Forks**: {repo['forkCount']}")
        body_lines.append(f"- **Last push**: {repo.get('pushedAt', 'N/A')[:10]}")
        if topics:
            body_lines.append(f"- **Topics**: {', '.join(topics)}")
        body_lines.append(f"- **Contributed**: Yes")
        write_md(base / "repositories" / f"{repo['name']}.md", frontmatter, "\n".join(body_lines))
        written += 1
        time.sleep(client.rate_limit_delay)

    typer.echo(f"✓  Contributed Repositories: {written} files written")
    return repos


# ---------------------------------------------------------------------------
# 2. Commits
# ---------------------------------------------------------------------------


def extract_commits(
    client: GitHubClient, base: Path, login: str, repos: list[dict], since: datetime
) -> list[dict]:
    typer.echo("→  Extracting commits…")
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    by_month: dict[str, list[dict]] = defaultdict(list)
    all_commits: list[dict] = []

    for repo in repos:
        repo_name = repo["name"]
        if repo.get("isFork"):
            continue

        cursor: Optional[str] = None
        while True:
            variables: dict[str, Any] = {
                "owner": login,
                "name": repo_name,
                "since": since_iso,
            }
            if cursor:
                variables["after"] = cursor

            data = client.graphql(_COMMIT_QUERY, variables)
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
                    "message": node["message"].split("\n")[0],
                    "date": node["committedDate"],
                    "additions": node.get("additions", 0),
                    "deletions": node.get("deletions", 0),
                }
                by_month[month].append(entry)
                all_commits.append(entry)

            if not history["pageInfo"]["hasNextPage"]:
                break
            cursor = history["pageInfo"]["endCursor"]
            time.sleep(client.rate_limit_delay)

        time.sleep(client.rate_limit_delay)

    for month, entries in sorted(by_month.items()):
        frontmatter: dict[str, Any] = {
            "period": month,
            "category": "commits",
            "total": len(entries),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        total_add = sum(e.get("additions", 0) for e in entries)
        total_del = sum(e.get("deletions", 0) for e in entries)
        lines = [f"## Commits — {month}", ""]
        lines.append(f"**Total: +{total_add} / -{total_del}**")
        lines.append("")
        for e in sorted(entries, key=lambda x: x["date"]):
            diff = f" (+{e.get('additions', 0)}/-{e.get('deletions', 0)})"
            lines.append(f"- `{e['date'][:10]}` **{e['repo']}** `{e['sha']}` {e['message']}{diff}")
        write_md(base / "commits" / f"{month}.md", frontmatter, "\n".join(lines))

    typer.echo(f"✓  Commits: {len(all_commits)} commits across {len(by_month)} months")
    return all_commits


# ---------------------------------------------------------------------------
# 3. Pull Requests & Reviews
# ---------------------------------------------------------------------------


def extract_pull_requests(
    client: GitHubClient, base: Path, login: str, since: datetime
) -> list[dict]:
    typer.echo("→  Extracting pull requests…")
    cursor: Optional[str] = None
    prs: list[dict] = []
    page = 0

    while True:
        variables: dict[str, Any] = {"login": login}
        if cursor:
            variables["after"] = cursor

        data = client.graphql(_PR_QUERY, variables)
        if not data:
            break

        page_data = data["user"]["pullRequests"]
        nodes = page_data["nodes"]

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
        time.sleep(client.rate_limit_delay)

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
        write_md(
            base / "pull_requests" / filename,
            frontmatter,
            "\n".join(body_lines),
        )

    typer.echo(f"✓  Pull Requests: {len(prs)} files written")
    return prs


# ---------------------------------------------------------------------------
# 4. READMEs
# ---------------------------------------------------------------------------


def extract_readmes(
    client: GitHubClient, base: Path, login: str, repos: list[dict]
) -> int:
    typer.echo("→  Archiving READMEs…")
    written = 0

    for repo in repos:
        repo_name = repo["name"]
        data = client.rest(f"/repos/{login}/{repo_name}/readme")

        if data is None:
            time.sleep(client.rate_limit_delay)
            continue

        if isinstance(data, dict) and "content" in data:
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        else:
            content = ""

        if not content.strip():
            time.sleep(client.rate_limit_delay)
            continue

        frontmatter: dict[str, Any] = {
            "repo": repo_name,
            "url": repo.get("url", ""),
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "category": "readme",
        }
        out_path = base / "readmes" / f"{repo_name}_readme.md"
        write_md(out_path, frontmatter, content)
        written += 1
        time.sleep(client.rate_limit_delay)

    typer.echo(f"✓  READMEs: {written} files archived")
    return written


# ---------------------------------------------------------------------------
# 5. Stars (GraphQL)
# ---------------------------------------------------------------------------

_STARS_QUERY = """
query($after: String) {
  viewer {
    starredRepositories(first: 100, after: $after, orderBy: {field: STARRED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      edges {
        starredAt
        node {
          nameWithOwner
          description
          url
          primaryLanguage { name }
          stargazerCount
          repositoryTopics(first: 10) { nodes { topic { name } } }
        }
      }
    }
  }
}
"""


def extract_stars(
    client: GitHubClient, base: Path, login: str, since: datetime,
) -> list[dict]:
    """GraphQL viewer.starredRepositories로 starred repos를 수집한다."""
    typer.echo("→  Extracting starred repositories…")

    by_month: dict[str, list[dict]] = defaultdict(list)
    all_stars: list[dict] = []
    cursor: Optional[str] = None

    while True:
        variables: dict[str, Any] = {}
        if cursor:
            variables["after"] = cursor

        data = client.graphql(_STARS_QUERY, variables)
        if not data:
            break

        starred = data["viewer"]["starredRepositories"]
        edges = starred["edges"]

        reached_cutoff = False
        for edge in edges:
            starred_at_str = edge["starredAt"]
            starred_at = _iso_to_dt(starred_at_str)

            if starred_at < since:
                reached_cutoff = True
                break

            node = edge["node"]
            lang = (node.get("primaryLanguage") or {}).get("name", "")
            topics = [t["topic"]["name"] for t in (node.get("repositoryTopics") or {}).get("nodes", [])]

            entry = {
                "starred_at": starred_at_str,
                "name": node.get("nameWithOwner", ""),
                "description": (node.get("description") or "").strip(),
                "url": node.get("url", ""),
                "language": lang,
                "topics": topics,
                "stars": node.get("stargazerCount", 0),
            }
            month = entry["starred_at"][:7]
            by_month[month].append(entry)
            all_stars.append(entry)

        if reached_cutoff or not starred["pageInfo"]["hasNextPage"]:
            break
        cursor = starred["pageInfo"]["endCursor"]
        time.sleep(client.rate_limit_delay)

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
            lines.append(f"- **Stars:** {e.get('stars', 0):,}")
            if e["description"]:
                lines.append(f"- **Description:** {e['description']}")
            if topic_str:
                lines.append(f"- **Topics:** {topic_str}")
            lines.append("")
        write_md(base / "stars" / f"{month}.md", frontmatter, "\n".join(lines))

    typer.echo(f"✓  Stars: {len(all_stars)} starred repos across {len(by_month)} months")
    return all_stars


# ---------------------------------------------------------------------------
# 6. Issues
# ---------------------------------------------------------------------------

_ISSUE_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    issues(
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
        closedAt
        url
        body
        repository { nameWithOwner }
        labels(first: 10) { nodes { name } }
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


def extract_issues(
    client: GitHubClient, base: Path, login: str, since: datetime
) -> list[dict]:
    """사용자가 생성한 이슈를 월별 MD 파일로 수집한다."""
    typer.echo("→  Extracting issues…")
    cursor: Optional[str] = None
    issues: list[dict] = []
    page = 0

    while True:
        variables: dict[str, Any] = {"login": login}
        if cursor:
            variables["after"] = cursor

        data = client.graphql(_ISSUE_QUERY, variables)
        if not data:
            break

        page_data = data["user"]["issues"]
        nodes = page_data["nodes"]

        reached_cutoff = False
        for node in nodes:
            created = _iso_to_dt(node["createdAt"])
            if created < since:
                reached_cutoff = True
                break
            issues.append(node)

        page += 1
        typer.echo(f"   page {page}: {len(issues)} issues so far")

        if reached_cutoff or not page_data["pageInfo"]["hasNextPage"]:
            break
        cursor = page_data["pageInfo"]["endCursor"]
        time.sleep(client.rate_limit_delay)

    # 월별 그룹핑
    by_month: dict[str, list[dict]] = defaultdict(list)
    for issue in issues:
        month = issue["createdAt"][:7]
        by_month[month].append(issue)

    for month, entries in sorted(by_month.items()):
        frontmatter: dict[str, Any] = {
            "period": month,
            "category": "issues",
            "total": len(entries),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        lines = [f"## Issues — {month}", ""]
        for e in sorted(entries, key=lambda x: x["createdAt"]):
            labels = [l["name"] for l in e.get("labels", {}).get("nodes", [])]
            label_str = f" [{', '.join(labels)}]" if labels else ""
            repo = e["repository"]["nameWithOwner"]
            lines.append(f"### #{e['number']}: {e['title']}{label_str}")
            lines.append(f"- **Repo:** {repo}")
            lines.append(f"- **State:** {e['state']}")
            lines.append(f"- **Created:** {e['createdAt'][:10]}")
            if e.get("closedAt"):
                lines.append(f"- **Closed:** {e['closedAt'][:10]}")
            if e.get("body", "").strip():
                lines.append(f"\n{e['body'].strip()[:300]}")

            comments = e.get("comments", {}).get("nodes", [])
            if comments:
                lines.append("")
                lines.append("**Comments:**")
                for c in comments:
                    author = (c.get("author") or {}).get("login", "unknown")
                    lines.append(f"- **{author}** ({c['createdAt'][:10]}): {c['body'].strip()[:200]}")
            lines.append("")

        write_md(base / "issues" / f"{month}.md", frontmatter, "\n".join(lines))

    typer.echo(f"✓  Issues: {len(issues)} issues across {len(by_month)} months")
    return issues


# ---------------------------------------------------------------------------
# 7. Code Reviews (as reviewer)
# ---------------------------------------------------------------------------

_REVIEW_CONTRIBUTIONS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!, $after: String) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      pullRequestReviewContributions(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          occurredAt
          pullRequestReview {
            state
            createdAt
            body
            pullRequest {
              title
              number
              url
              repository { nameWithOwner }
            }
          }
        }
      }
    }
  }
}
"""


def extract_reviews(
    client: GitHubClient, base: Path, login: str, since: datetime
) -> list[dict]:
    """다른 사람 PR에 남긴 코드 리뷰를 월별 MD 파일로 수집한다."""
    typer.echo("→  Extracting code reviews…")
    cursor: Optional[str] = None
    reviews: list[dict] = []
    now = datetime.now(timezone.utc)

    while True:
        variables: dict[str, Any] = {
            "login": login,
            "from": since.isoformat(),
            "to": now.isoformat(),
        }
        if cursor:
            variables["after"] = cursor

        data = client.graphql(_REVIEW_CONTRIBUTIONS_QUERY, variables)
        if not data:
            break

        contributions = data["user"]["contributionsCollection"]["pullRequestReviewContributions"]
        nodes = contributions["nodes"]

        for node in nodes:
            occurred = _iso_to_dt(node["occurredAt"])
            if occurred < since:
                continue
            review = node["pullRequestReview"]
            pr = review["pullRequest"]
            reviews.append({
                "date": node["occurredAt"],
                "state": review["state"],
                "body": review.get("body", ""),
                "pr_title": pr["title"],
                "pr_number": pr["number"],
                "pr_url": pr["url"],
                "repository": pr["repository"]["nameWithOwner"],
            })

        if not contributions["pageInfo"]["hasNextPage"]:
            break
        cursor = contributions["pageInfo"]["endCursor"]
        time.sleep(client.rate_limit_delay)

    # 월별 그룹핑
    by_month: dict[str, list[dict]] = defaultdict(list)
    for r in reviews:
        month = r["date"][:7]
        by_month[month].append(r)

    for month, entries in sorted(by_month.items()):
        frontmatter: dict[str, Any] = {
            "period": month,
            "category": "reviews",
            "total": len(entries),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        lines = [f"## Code Reviews — {month}", ""]
        for e in sorted(entries, key=lambda x: x["date"]):
            lines.append(f"- `{e['date'][:10]}` **{e['repository']}** PR #{e['pr_number']}: {e['pr_title']} [{e['state']}]")
            if e.get("body", "").strip():
                lines.append(f"  > {e['body'].strip()[:200]}")
        write_md(base / "reviews" / f"{month}.md", frontmatter, "\n".join(lines))

    typer.echo(f"✓  Code Reviews: {len(reviews)} reviews across {len(by_month)} months")
    return reviews


# ---------------------------------------------------------------------------
# 8. Projects
# ---------------------------------------------------------------------------

_PROJECT_QUERY = """
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


def extract_projects(client: GitHubClient, base: Path, login: str) -> list[dict]:
    typer.echo("→  Extracting GitHub Projects…")
    cursor: Optional[str] = None
    projects: list[dict] = []

    while True:
        variables: dict[str, Any] = {"login": login}
        if cursor:
            variables["after"] = cursor

        data = client.graphql(_PROJECT_QUERY, variables)
        if not data:
            break

        page_data = data["user"]["projectsV2"]
        projects.extend(page_data["nodes"])

        if not page_data["pageInfo"]["hasNextPage"]:
            break
        cursor = page_data["pageInfo"]["endCursor"]
        time.sleep(client.rate_limit_delay)

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
        write_md(
            base / "projects" / f"project_{proj['number']}_{safe_title}.md",
            frontmatter,
            body,
        )

    typer.echo(f"✓  Projects: {len(projects)} files written")
    return projects


# ---------------------------------------------------------------------------
# 7. Organizations
# ---------------------------------------------------------------------------


def extract_organizations(client: GitHubClient, base: Path, login: str) -> list[dict]:
    typer.echo("→  Extracting organizations…")
    data = client.rest("/user/orgs")
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
        write_md(
            base / "organizations" / f"{org.get('login', 'unknown')}.md",
            frontmatter,
            body,
        )

    typer.echo(f"✓  Organizations: {len(data)} files written")
    return data
