"""Markdown, JSON, CSV 출력 함수."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_md(path: Path, frontmatter: dict[str, Any], body: str = "") -> None:
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
    subdirs: list[str],
    issues: list[dict] | None = None,
    reviews: list[dict] | None = None,
) -> dict[str, Any]:
    """Write metadata.json and return the metadata dict."""
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_user": login,
        "period_days": days,
        "summary": {
            "repositories": len(repos),
            "commits": len(commits),
            "pull_requests": len(prs),
            "issues": len(issues or []),
            "reviews": len(reviews or []),
            "stars": len(stars),
            "projects": len(projects),
            "organizations": len(orgs),
        },
        "directories": {d: f"{d}/" for d in subdirs},
        "top_languages": _top_languages(repos),
        "top_starred_languages": _top_languages_from_stars(stars),
    }
    (base / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return meta


def generate_timeline(
    base: Path,
    commits: list[dict],
    prs: list[dict],
    stars: list[dict],
    issues: list[dict] | None = None,
    reviews: list[dict] | None = None,
) -> list[dict[str, str]]:
    """Write timeline.csv and return the rows."""
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

    for issue in (issues or []):
        rows.append(
            {
                "date": issue["createdAt"][:10],
                "category": "Issue",
                "repository": issue["repository"]["nameWithOwner"],
                "action": f"[{issue['state']}] {issue['title'][:120]}",
            }
        )

    for r in (reviews or []):
        rows.append(
            {
                "date": r["date"][:10],
                "category": "Review",
                "repository": r["repository"],
                "action": f"[{r['state']}] PR #{r['pr_number']}: {r['pr_title'][:100]}",
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

    return rows


def generate_summary(
    base: Path,
    login: str,
    days: int,
    repos: list[dict],
    commits: list[dict],
    prs: list[dict],
    issues: list[dict],
    reviews: list[dict],
    stars: list[dict],
    projects: list[dict],
    orgs: list[dict],
) -> None:
    """Write SUMMARY.md — LLM/사람이 한눈에 파악하는 활동 리포트."""
    lines = [
        f"# GitHub Activity Summary — {login}",
        "",
        f"Period: last {days} days",
        "",
        "## Overview",
        "",
        "| Category | Count |",
        "|---|---|",
        f"| Repositories | {len(repos)} |",
        f"| Commits | {len(commits)} |",
        f"| Pull Requests | {len(prs)} |",
        f"| Issues | {len(issues)} |",
        f"| Code Reviews | {len(reviews)} |",
        f"| Stars | {len(stars)} |",
        f"| Projects | {len(projects)} |",
        f"| Organizations | {len(orgs)} |",
        "",
    ]

    # Monthly Activity
    monthly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in commits:
        monthly[c["date"][:7]]["commits"] += 1
    for pr in prs:
        monthly[pr["createdAt"][:7]]["prs"] += 1
    for issue in issues:
        monthly[issue["createdAt"][:7]]["issues"] += 1
    for r in reviews:
        monthly[r["date"][:7]]["reviews"] += 1

    lines.append("## Monthly Activity")
    lines.append("")
    if monthly:
        lines.append("| Month | Commits | PRs | Issues | Reviews |")
        lines.append("|---|---|---|---|---|")
        for month in sorted(monthly.keys()):
            m = monthly[month]
            lines.append(f"| {month} | {m['commits']} | {m['prs']} | {m['issues']} | {m['reviews']} |")
    else:
        lines.append("No activity recorded.")
    lines.append("")

    # Top Languages
    langs = _top_languages(repos)
    lines.append("## Top Languages")
    lines.append("")
    if langs:
        for lang, count in langs.items():
            lines.append(f"- **{lang}**: {count} repos")
    else:
        lines.append("No language data.")
    lines.append("")

    # Most Active Repos
    repo_commits: dict[str, int] = defaultdict(int)
    for c in commits:
        repo_commits[c["repo"]] += 1
    if repo_commits:
        lines.append("## Most Active Repositories")
        lines.append("")
        for repo, count in sorted(repo_commits.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"- **{repo}**: {count} commits")
        lines.append("")

    # Recent PRs
    if prs:
        lines.append("## Recent Pull Requests")
        lines.append("")
        for pr in sorted(prs, key=lambda x: x["createdAt"], reverse=True)[:10]:
            repo = pr["repository"]["nameWithOwner"]
            lines.append(f"- [{pr['state']}] **{repo}** #{pr.get('number', '')} {pr['title']}")
        lines.append("")

    (base / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
