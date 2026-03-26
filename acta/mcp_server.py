"""Acta Ergo Sum — MCP Server.

FastMCP 기반으로 레포 딥 분석 도구를 MCP 프로토콜로 노출한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from acta.client import GitHubClient
from acta.deep.collector import DeepCollector
from acta.deep.detector import (
    build_tree_summary,
    count_by_extension,
    detect_entry_points,
    detect_key_files,
)
from acta.deep.renderer import (
    render_community,
    render_evolution,
    render_overview,
    render_structure,
    render_tech_stack,
)

mcp = FastMCP(
    "acta-ergo-sum",
    description="GitHub 레포지토리를 분석하여 프로젝트 구조, 기술 스택, 설계 의도를 LLM에 제공합니다.",
)


def _parse_repo(repo: str) -> tuple[str, str]:
    """'owner/repo' 문자열을 (owner, repo) 튜플로 파싱한다."""
    parts = repo.strip().split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid repo format: {repo!r}. Expected 'owner/repo'.")
    return parts[0], parts[1]


def _get_collector(repo: str) -> DeepCollector:
    owner, name = _parse_repo(repo)
    return DeepCollector(GitHubClient(rate_limit_delay=0.2), owner, name)


# ---------------------------------------------------------------------------
# Tool 1: deep_analyze_repo — 전체 딥 분석
# ---------------------------------------------------------------------------

@mcp.tool()
def deep_analyze_repo(
    repo: str,
    sections: list[str] | None = None,
    include_my_contributions: bool = False,
) -> str:
    """GitHub 레포지토리를 분석하여 프로젝트 구조, 기술 스택, 설계 의도를 추출합니다.

    Args:
        repo: 분석할 레포 (예: "owner/repo")
        sections: 포함할 섹션 목록. None이면 전체.
            가능한 값: overview, structure, tech_stack, evolution, community
        include_my_contributions: 내 기여 분석 포함 여부
    """
    collector = _get_collector(repo)
    all_sections = sections or ["overview", "structure", "tech_stack", "evolution", "community"]

    results: list[str] = []

    overview_data: dict[str, Any] = {}
    tree_paths: list[str] = []
    languages: dict[str, int] = {}

    # 공통 데이터 수집
    if any(s in all_sections for s in ["overview", "community"]):
        overview_data = collector.fetch_overview()

    if any(s in all_sections for s in ["structure", "tech_stack"]):
        tree_paths = collector.fetch_tree()
        languages = collector.fetch_languages()

    # 섹션별 렌더링
    if "overview" in all_sections:
        readme = collector.fetch_readme()
        _, body = render_overview(overview_data, readme)
        results.append(body)

    if "structure" in all_sections:
        _, body = render_structure(tree_paths, languages)
        results.append(body)

    if "tech_stack" in all_sections:
        key_files = detect_key_files(tree_paths)
        contents: dict[str, str] = {}
        for _cat, paths in key_files.items():
            for path in paths[:3]:  # 카테고리당 3개 제한
                content = collector.fetch_file_content(path)
                if content:
                    contents[path] = content
        deps = collector.fetch_dependencies()
        _, body = render_tech_stack(languages, contents, deps)
        results.append(body)

    if "evolution" in all_sections:
        releases = collector.fetch_releases()
        changelog = ""
        if "CHANGELOG.md" in tree_paths:
            changelog = collector.fetch_file_content("CHANGELOG.md")
        elif "CHANGES.md" in tree_paths:
            changelog = collector.fetch_file_content("CHANGES.md")
        commits = collector.fetch_recent_commits()
        _, body = render_evolution(releases, changelog, commits)
        results.append(body)

    if "community" in all_sections:
        health = collector.fetch_community_health()
        labels = collector.fetch_issue_labels()
        _, body = render_community(health, labels, overview_data)
        results.append(body)

    if include_my_contributions:
        client = GitHubClient(rate_limit_delay=0.2)
        login = client.get_authenticated_user()
        stats = collector.fetch_my_contributions(login)
        if stats:
            from acta.deep.renderer import render_my_contribution
            _, body = render_my_contribution(stats, login, repo)
            results.append(body)

    return "\n\n---\n\n".join(results)


# ---------------------------------------------------------------------------
# Tool 2: get_repo_structure — 구조만 빠르게
# ---------------------------------------------------------------------------

@mcp.tool()
def get_repo_structure(repo: str, depth: int = 3) -> str:
    """레포지토리의 디렉토리 트리와 파일 분포를 반환합니다.

    Args:
        repo: 분석할 레포 (예: "owner/repo")
        depth: 트리 표시 깊이 (기본 3)
    """
    collector = _get_collector(repo)
    tree_paths = collector.fetch_tree()
    languages = collector.fetch_languages()

    if not tree_paths:
        return f"Could not fetch tree for {repo}"

    lines = [f"# {repo} — Structure", ""]
    lines.append(f"**Total files**: {len(tree_paths)}")
    lines.append("")

    # Languages
    total_bytes = sum(languages.values())
    if total_bytes:
        lines.append("## Languages")
        for lang, b in sorted(languages.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"- {lang}: {b / total_bytes * 100:.1f}%")
        lines.append("")

    # Extensions
    ext_counts = count_by_extension(tree_paths)
    lines.append("## File Types")
    for ext, count in list(ext_counts.items())[:15]:
        lines.append(f"- `{ext}`: {count}")
    lines.append("")

    # Tree
    lines.append("## Tree")
    lines.append("```")
    lines.append(build_tree_summary(tree_paths, max_depth=depth))
    lines.append("```")

    # Key files
    key_files = detect_key_files(tree_paths)
    if key_files:
        lines.append("")
        lines.append("## Key Files")
        for cat, files in key_files.items():
            lines.append(f"- **{cat}**: {', '.join(f'`{f}`' for f in files)}")

    # Entry points
    entries = detect_entry_points(tree_paths)
    if entries:
        lines.append("")
        lines.append("## Entry Points")
        for ep in entries:
            lines.append(f"- `{ep}`")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3: get_repo_key_files — 핵심 파일 내용
# ---------------------------------------------------------------------------

@mcp.tool()
def get_repo_key_files(
    repo: str,
    category: str | None = None,
) -> str:
    """레포지토리의 핵심 설정 파일 내용을 반환합니다.

    Args:
        repo: 분석할 레포 (예: "owner/repo")
        category: 파일 카테고리 필터. None이면 전체.
            가능한 값: manifest, infra, ci, docs, config
    """
    collector = _get_collector(repo)
    tree_paths = collector.fetch_tree()

    if not tree_paths:
        return f"Could not fetch tree for {repo}"

    key_files = detect_key_files(tree_paths, category=category)
    if not key_files:
        cat_str = f" in category '{category}'" if category else ""
        return f"No key files detected{cat_str} for {repo}"

    lines = [f"# {repo} — Key Files", ""]

    for cat, paths in key_files.items():
        lines.append(f"## {cat.title()}")
        lines.append("")
        for path in paths:
            content = collector.fetch_file_content(path)
            if content:
                ext = path.rsplit(".", 1)[-1] if "." in path else ""
                lines.append(f"### `{path}`")
                lines.append("")
                lines.append(f"```{ext}")
                if len(content) > 3000:
                    lines.append(content[:3000])
                    lines.append(f"\n… (truncated, {len(content)} chars)")
                else:
                    lines.append(content)
                lines.append("```")
                lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4: get_repo_evolution — 진화 내러티브
# ---------------------------------------------------------------------------

@mcp.tool()
def get_repo_evolution(repo: str, limit: int = 20) -> str:
    """릴리스 노트, 커밋 히스토리, CHANGELOG에서 프로젝트 진화 내러티브를 추출합니다.

    Args:
        repo: 분석할 레포 (예: "owner/repo")
        limit: 릴리스/커밋 최대 수 (기본 20)
    """
    collector = _get_collector(repo)

    releases = collector.fetch_releases()
    commits = collector.fetch_recent_commits(limit=limit)

    # CHANGELOG 검색
    tree_paths = collector.fetch_tree()
    changelog = ""
    for fname in ["CHANGELOG.md", "CHANGES.md", "HISTORY.md"]:
        if fname in tree_paths:
            changelog = collector.fetch_file_content(fname)
            break

    _, body = render_evolution(releases, changelog, commits)
    return body


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------


def run_server() -> None:
    """MCP 서버를 시작한다."""
    mcp.run()
