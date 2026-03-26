"""마크다운 렌더링 — 딥 분석 결과를 MD로 변환한다."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acta.deep.detector import (
    build_tree_summary,
    count_by_extension,
    detect_entry_points,
    detect_key_files,
)
from acta.writers import write_md


def _lang_percentages(languages: dict[str, int]) -> list[str]:
    total = sum(languages.values())
    if total == 0:
        return []
    return [
        f"{lang}: {bytes_val / total * 100:.1f}%"
        for lang, bytes_val in sorted(languages.items(), key=lambda x: -x[1])
    ]


# ---------------------------------------------------------------------------
# Section Renderers
# ---------------------------------------------------------------------------


def render_overview(
    repo_meta: dict[str, Any],
    readme: str,
) -> tuple[dict[str, Any], str]:
    """overview 섹션의 frontmatter와 body를 반환한다."""
    topics = [n["topic"]["name"] for n in repo_meta.get("repositoryTopics", {}).get("nodes", [])]
    license_info = repo_meta.get("licenseInfo") or {}
    parent = repo_meta.get("parent") or {}
    lang = (repo_meta.get("primaryLanguage") or {}).get("name", "")

    frontmatter: dict[str, Any] = {
        "name": repo_meta.get("nameWithOwner", ""),
        "url": repo_meta.get("url", ""),
        "description": (repo_meta.get("description") or "").strip(),
        "language": lang,
        "license": license_info.get("spdxId", ""),
        "stars": repo_meta.get("stargazerCount", 0),
        "forks": repo_meta.get("forkCount", 0),
        "created_at": repo_meta.get("createdAt", ""),
        "topics": topics,
        "category": "deep_overview",
    }

    lines = [f"# {repo_meta.get('nameWithOwner', '')}"]
    lines.append("")
    if repo_meta.get("description"):
        lines.append(f"> {repo_meta['description']}")
        lines.append("")

    lines.append("## Metadata")
    lines.append("")
    lines.append(f"- **Language**: {lang or 'N/A'}")
    lines.append(f"- **License**: {license_info.get('name', 'N/A')}")
    lines.append(f"- **Created**: {repo_meta.get('createdAt', '')[:10]}")
    lines.append(f"- **Last push**: {repo_meta.get('pushedAt', '')[:10]}")
    lines.append(f"- **Stars**: {repo_meta.get('stargazerCount', 0):,} | **Forks**: {repo_meta.get('forkCount', 0):,} | **Watchers**: {repo_meta.get('watchers', {}).get('totalCount', 0):,}")

    open_issues = repo_meta.get("issues", {}).get("totalCount", 0)
    closed_issues = repo_meta.get("closedIssues", {}).get("totalCount", 0)
    open_prs = repo_meta.get("pullRequests", {}).get("totalCount", 0)
    merged_prs = repo_meta.get("mergedPullRequests", {}).get("totalCount", 0)
    lines.append(f"- **Issues**: {open_issues} open / {closed_issues} closed")
    lines.append(f"- **PRs**: {open_prs} open / {merged_prs} merged")

    if topics:
        lines.append(f"- **Topics**: {', '.join(topics)}")
    if repo_meta.get("isArchived"):
        lines.append("- **Archived**: Yes")
    if repo_meta.get("isFork") and parent:
        lines.append(f"- **Forked from**: [{parent.get('nameWithOwner', '')}]({parent.get('url', '')})")
    if repo_meta.get("homepageUrl"):
        lines.append(f"- **Homepage**: {repo_meta['homepageUrl']}")

    funding = repo_meta.get("fundingLinks") or []
    if funding:
        lines.append("")
        lines.append("## Funding")
        for f in funding:
            lines.append(f"- {f.get('platform', '')}: {f.get('url', '')}")

    if readme:
        lines.append("")
        lines.append("## README")
        lines.append("")
        lines.append(readme)

    return frontmatter, "\n".join(lines)


def render_structure(
    tree_paths: list[str],
    languages: dict[str, int],
) -> tuple[dict[str, Any], str]:
    """structure 섹션의 frontmatter와 body를 반환한다."""
    ext_counts = count_by_extension(tree_paths)
    lang_pcts = _lang_percentages(languages)

    frontmatter: dict[str, Any] = {
        "total_files": len(tree_paths),
        "extensions": len(ext_counts),
        "category": "deep_structure",
    }

    lines = ["# Project Structure", ""]
    lines.append(f"**Total files**: {len(tree_paths)}")
    lines.append("")

    # Language breakdown
    if lang_pcts:
        lines.append("## Languages")
        lines.append("")
        for lp in lang_pcts[:15]:
            lines.append(f"- {lp}")
        lines.append("")

    # Extension distribution
    if ext_counts:
        lines.append("## File Types")
        lines.append("")
        lines.append("| Extension | Count |")
        lines.append("|---|---|")
        for ext, count in list(ext_counts.items())[:20]:
            lines.append(f"| `{ext}` | {count} |")
        lines.append("")

    # Directory tree
    lines.append("## Directory Tree")
    lines.append("")
    lines.append("```")
    lines.append(build_tree_summary(tree_paths, max_depth=3))
    lines.append("```")

    # Key files detected
    key_files = detect_key_files(tree_paths)
    if key_files:
        lines.append("")
        lines.append("## Key Files Detected")
        lines.append("")
        for cat, files in key_files.items():
            lines.append(f"### {cat.title()}")
            for f in files:
                lines.append(f"- `{f}`")
            lines.append("")

    # Entry points
    entry_points = detect_entry_points(tree_paths)
    if entry_points:
        lines.append("## Entry Points (estimated)")
        lines.append("")
        for ep in entry_points:
            lines.append(f"- `{ep}`")

    return frontmatter, "\n".join(lines)


def render_tech_stack(
    languages: dict[str, int],
    key_file_contents: dict[str, str],
    dependencies: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """tech_stack 섹션의 frontmatter와 body를 반환한다."""
    lang_pcts = _lang_percentages(languages)

    # 의존성 패키지 매니저별 집계
    dep_by_manager: dict[str, list[str]] = {}
    for manifest in dependencies:
        filename = manifest.get("filename", "")
        deps = manifest.get("dependencies", {}).get("nodes", [])
        for dep in deps:
            manager = dep.get("packageManager", "UNKNOWN")
            pkg = dep.get("packageName", "")
            req = dep.get("requirements", "")
            entry = f"{pkg} {req}".strip() if req else pkg
            dep_by_manager.setdefault(manager, []).append(entry)

    frontmatter: dict[str, Any] = {
        "languages": [lp.split(":")[0] for lp in lang_pcts[:5]],
        "dependency_managers": list(dep_by_manager.keys()),
        "category": "deep_tech_stack",
    }

    lines = ["# Tech Stack", ""]

    # Languages
    if lang_pcts:
        lines.append("## Languages")
        lines.append("")
        for lp in lang_pcts[:10]:
            lines.append(f"- {lp}")
        lines.append("")

    # Dependencies
    if dep_by_manager:
        lines.append("## Dependencies")
        lines.append("")
        for manager, deps in sorted(dep_by_manager.items()):
            lines.append(f"### {manager} ({len(deps)} packages)")
            lines.append("")
            for dep in sorted(deps)[:50]:
                lines.append(f"- `{dep}`")
            if len(deps) > 50:
                lines.append(f"- … and {len(deps) - 50} more")
            lines.append("")

    # Key file contents
    if key_file_contents:
        lines.append("## Configuration Files")
        lines.append("")
        for path, content in key_file_contents.items():
            lines.append(f"### `{path}`")
            lines.append("")
            ext = path.rsplit(".", 1)[-1] if "." in path else ""
            lines.append(f"```{ext}")
            # 길이 제한 (토큰 절약)
            if len(content) > 3000:
                lines.append(content[:3000])
                lines.append(f"\n… (truncated, {len(content)} chars total)")
            else:
                lines.append(content)
            lines.append("```")
            lines.append("")

    return frontmatter, "\n".join(lines)


def render_evolution(
    releases: list[dict[str, Any]],
    changelog: str,
    recent_commits: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """evolution 섹션의 frontmatter와 body를 반환한다."""
    frontmatter: dict[str, Any] = {
        "releases_count": len(releases),
        "commits_sampled": len(recent_commits),
        "category": "deep_evolution",
    }

    lines = ["# Project Evolution", ""]

    # Releases
    if releases:
        lines.append("## Releases")
        lines.append("")
        for rel in releases:
            tag = rel.get("tagName", "")
            name = rel.get("name", "") or tag
            date = (rel.get("publishedAt") or "")[:10]
            pre = " (pre-release)" if rel.get("isPrerelease") else ""
            lines.append(f"### {name}{pre} — {date}")
            desc = (rel.get("description") or "").strip()
            if desc:
                # 릴리스 노트 길이 제한
                if len(desc) > 1000:
                    desc = desc[:1000] + "\n\n… (truncated)"
                lines.append("")
                lines.append(desc)
            lines.append("")
    else:
        lines.append("## Releases")
        lines.append("")
        lines.append("No releases published.")
        lines.append("")

    # CHANGELOG
    if changelog:
        lines.append("## CHANGELOG")
        lines.append("")
        if len(changelog) > 5000:
            lines.append(changelog[:5000])
            lines.append(f"\n… (truncated, {len(changelog)} chars total)")
        else:
            lines.append(changelog)
        lines.append("")

    # Recent commits summary
    if recent_commits:
        lines.append("## Recent Commits")
        lines.append("")
        for commit in recent_commits[:30]:
            c = commit.get("commit", {})
            sha = commit.get("sha", "")[:7]
            msg = c.get("message", "").split("\n")[0][:120]
            date = (c.get("author", {}).get("date", "") or "")[:10]
            author = (commit.get("author") or {}).get("login", "")
            if not author:
                author = c.get("author", {}).get("name", "")
            lines.append(f"- `{date}` `{sha}` **{author}** — {msg}")

    return frontmatter, "\n".join(lines)


def render_community(
    health: dict[str, Any],
    labels: list[dict[str, Any]],
    overview: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """community 섹션의 frontmatter와 body를 반환한다."""
    health_pct = health.get("health_percentage", 0)
    files = health.get("files", {})

    frontmatter: dict[str, Any] = {
        "health_percentage": health_pct,
        "category": "deep_community",
    }

    lines = ["# Community & Governance", ""]

    # Health score
    lines.append(f"## Community Health: {health_pct}%")
    lines.append("")

    standard_files = [
        ("README", files.get("readme")),
        ("LICENSE", files.get("license")),
        ("CONTRIBUTING", files.get("contributing")),
        ("CODE_OF_CONDUCT", files.get("code_of_conduct")),
        ("ISSUE_TEMPLATE", files.get("issue_template")),
        ("PULL_REQUEST_TEMPLATE", files.get("pull_request_template")),
    ]
    for name, info in standard_files:
        present = "Yes" if info else "No"
        lines.append(f"- **{name}**: {present}")
    lines.append("")

    # Code of conduct from overview
    coc = overview.get("codeOfConduct")
    if coc:
        lines.append(f"**Code of Conduct**: {coc.get('name', '')}")
        lines.append("")

    # Issue labels
    if labels:
        lines.append("## Issue Labels")
        lines.append("")
        lines.append("| Label | Issues |")
        lines.append("|---|---|")
        sorted_labels = sorted(labels, key=lambda x: -(x.get("issues", {}).get("totalCount", 0)))
        for label in sorted_labels[:25]:
            count = label.get("issues", {}).get("totalCount", 0)
            if count > 0:
                lines.append(f"| `{label['name']}` | {count} |")
        lines.append("")

    return frontmatter, "\n".join(lines)


def render_my_contribution(
    stats: dict[str, Any],
    login: str,
    repo_name: str,
) -> tuple[dict[str, Any], str]:
    """my_contribution 섹션의 frontmatter와 body를 반환한다."""
    if not stats:
        return {}, ""

    total_commits = stats.get("total", 0)
    weeks = stats.get("weeks", [])
    total_add = sum(w.get("a", 0) for w in weeks)
    total_del = sum(w.get("d", 0) for w in weeks)

    frontmatter: dict[str, Any] = {
        "login": login,
        "repository": repo_name,
        "total_commits": total_commits,
        "total_additions": total_add,
        "total_deletions": total_del,
        "category": "deep_my_contribution",
    }

    lines = [f"# My Contribution to {repo_name}", ""]
    lines.append(f"**Author**: {login}")
    lines.append(f"**Total commits**: {total_commits}")
    lines.append(f"**Lines**: +{total_add:,} / -{total_del:,}")
    lines.append("")

    # 주간 활동 (0이 아닌 주만)
    active_weeks = [w for w in weeks if w.get("c", 0) > 0]
    if active_weeks:
        lines.append("## Weekly Activity")
        lines.append("")
        lines.append("| Week | Commits | +Lines | -Lines |")
        lines.append("|---|---|---|---|")
        for w in active_weeks[-20:]:  # 최근 20주
            from datetime import datetime
            date = datetime.fromtimestamp(w["w"], tz=timezone.utc).strftime("%Y-%m-%d")
            lines.append(f"| {date} | {w.get('c', 0)} | +{w.get('a', 0)} | -{w.get('d', 0)} |")

    return frontmatter, "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def render_all_sections(
    base: Path,
    overview: dict[str, Any],
    readme: str,
    tree_paths: list[str],
    languages: dict[str, int],
    key_file_contents: dict[str, str],
    dependencies: list[dict[str, Any]],
    releases: list[dict[str, Any]],
    changelog: str,
    recent_commits: list[dict[str, Any]],
    health: dict[str, Any],
    labels: list[dict[str, Any]],
    my_stats: dict[str, Any] | None = None,
    login: str = "",
) -> dict[str, str]:
    """모든 섹션을 렌더링하고 파일로 저장한다. stdout 모드용 dict도 반환."""
    sections: dict[str, str] = {}

    renderers = [
        ("overview", lambda: render_overview(overview, readme)),
        ("structure", lambda: render_structure(tree_paths, languages)),
        ("tech_stack", lambda: render_tech_stack(languages, key_file_contents, dependencies)),
        ("evolution", lambda: render_evolution(releases, changelog, recent_commits)),
        ("community", lambda: render_community(health, labels, overview)),
    ]

    for name, render_fn in renderers:
        fm, body = render_fn()
        if body:
            write_md(base / f"{name}.md", fm, body)
            sections[name] = body

    if my_stats and login:
        repo_name = overview.get("nameWithOwner", "")
        fm, body = render_my_contribution(my_stats, login, repo_name)
        if body:
            write_md(base / "my_contribution.md", fm, body)
            sections["my_contribution"] = body

    # metadata.json
    import json
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": overview.get("nameWithOwner", ""),
        "sections": list(sections.keys()),
        "total_files_in_repo": len(tree_paths),
        "languages_detected": len(languages),
    }
    (base / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return sections
