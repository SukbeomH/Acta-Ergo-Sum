"""GitHub API 데이터 수집 — 레포 딥 분석용."""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import typer

from acta.client import GitHubClient


# ---------------------------------------------------------------------------
# GraphQL Queries
# ---------------------------------------------------------------------------

_REPO_OVERVIEW_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    name
    nameWithOwner
    description
    url
    homepageUrl
    createdAt
    updatedAt
    pushedAt
    isArchived
    isFork
    isPrivate
    isTemplate
    stargazerCount
    forkCount
    watchers { totalCount }
    issues(states: [OPEN]) { totalCount }
    closedIssues: issues(states: [CLOSED]) { totalCount }
    pullRequests(states: [OPEN]) { totalCount }
    mergedPullRequests: pullRequests(states: [MERGED]) { totalCount }
    primaryLanguage { name }
    licenseInfo { name spdxId url }
    repositoryTopics(first: 20) { nodes { topic { name } } }
    defaultBranchRef { name target { oid } }
    parent { nameWithOwner url }
    fundingLinks { platform url }
    codeOfConduct { name url }
  }
}
"""

_RELEASES_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    releases(first: 20, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        name
        tagName
        publishedAt
        description
        isPrerelease
        isDraft
      }
    }
  }
}
"""

_DEPENDENCY_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    dependencyGraphManifests(first: 10) {
      nodes {
        filename
        dependenciesCount
        dependencies(first: 100) {
          nodes {
            packageName
            requirements
            hasDependencies
            packageManager
          }
        }
      }
    }
  }
}
"""

_ISSUE_LABELS_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    labels(first: 50, orderBy: {field: NAME, direction: ASC}) {
      nodes {
        name
        issues { totalCount }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class DeepCollector:
    """특정 레포지토리에 대한 딥 분석 데이터를 수집한다."""

    def __init__(self, client: GitHubClient, owner: str, repo: str):
        self.client = client
        self.owner = owner
        self.repo = repo

    def _gql(self, query: str, extra_vars: dict[str, Any] | None = None) -> Any:
        variables = {"owner": self.owner, "name": self.repo}
        if extra_vars:
            variables.update(extra_vars)
        return self.client.graphql(query, variables)

    # -- Overview --

    def fetch_overview(self) -> dict[str, Any]:
        """레포 기본 메타데이터를 가져온다."""
        typer.echo("  → overview…")
        data = self._gql(_REPO_OVERVIEW_QUERY)
        if not data or "repository" not in data:
            return {}
        return data["repository"]

    def fetch_readme(self) -> str:
        """README 내용을 가져온다."""
        typer.echo("  → readme…")
        data = self.client.rest(f"/repos/{self.owner}/{self.repo}/readme")
        if not data or not isinstance(data, dict) or "content" not in data:
            return ""
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return ""

    # -- Structure --

    def fetch_tree(self) -> list[str]:
        """전체 파일 트리를 가져온다 (recursive)."""
        typer.echo("  → file tree…")
        # default branch의 tree SHA 필요
        ref_data = self.client.rest(f"/repos/{self.owner}/{self.repo}/git/ref/heads/main")
        if not ref_data or not isinstance(ref_data, dict):
            # main이 아닌 경우 master 시도
            ref_data = self.client.rest(f"/repos/{self.owner}/{self.repo}/git/ref/heads/master")
        if not ref_data or not isinstance(ref_data, dict):
            return []

        commit_sha = ref_data.get("object", {}).get("sha", "")
        if not commit_sha:
            return []

        # commit에서 tree SHA
        commit_data = self.client.rest(f"/repos/{self.owner}/{self.repo}/git/commits/{commit_sha}")
        if not commit_data or not isinstance(commit_data, dict):
            return []

        tree_sha = commit_data.get("tree", {}).get("sha", "")
        if not tree_sha:
            return []

        tree_data = self.client.rest(
            f"/repos/{self.owner}/{self.repo}/git/trees/{tree_sha}",
            recursive="1",
        )
        if not tree_data or not isinstance(tree_data, dict):
            return []

        paths = []
        for item in tree_data.get("tree", []):
            if item.get("type") == "blob":
                paths.append(item["path"])
        return paths

    def fetch_languages(self) -> dict[str, int]:
        """언어별 바이트 비율을 가져온다."""
        typer.echo("  → languages…")
        data = self.client.rest(f"/repos/{self.owner}/{self.repo}/languages")
        if not isinstance(data, dict):
            return {}
        return data

    # -- Tech Stack --

    def fetch_file_content(self, path: str) -> str:
        """특정 파일의 내용을 가져온다."""
        data = self.client.rest(f"/repos/{self.owner}/{self.repo}/contents/{path}")
        if not data or not isinstance(data, dict) or "content" not in data:
            return ""
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return ""

    def fetch_dependencies(self) -> list[dict[str, Any]]:
        """의존성 그래프 매니페스트를 가져온다."""
        typer.echo("  → dependencies…")
        data = self._gql(_DEPENDENCY_QUERY)
        if not data or "repository" not in data:
            return []
        manifests = data["repository"].get("dependencyGraphManifests", {}).get("nodes", [])
        return manifests

    def fetch_community_health(self) -> dict[str, Any]:
        """커뮤니티 프로필(건강도)을 가져온다."""
        typer.echo("  → community health…")
        data = self.client.rest(f"/repos/{self.owner}/{self.repo}/community/profile")
        if not isinstance(data, dict):
            return {}
        return data

    # -- Evolution --

    def fetch_releases(self) -> list[dict[str, Any]]:
        """최근 릴리스를 가져온다."""
        typer.echo("  → releases…")
        data = self._gql(_RELEASES_QUERY)
        if not data or "repository" not in data:
            return []
        return data["repository"].get("releases", {}).get("nodes", [])

    def fetch_recent_commits(self, limit: int = 100) -> list[dict[str, Any]]:
        """최근 커밋을 가져온다."""
        typer.echo("  → recent commits…")
        data = self.client.rest(
            f"/repos/{self.owner}/{self.repo}/commits",
            per_page=str(limit),
        )
        if not isinstance(data, list):
            return []
        return data

    # -- Community --

    def fetch_issue_labels(self) -> list[dict[str, Any]]:
        """이슈 라벨 분포를 가져온다."""
        typer.echo("  → issue labels…")
        data = self._gql(_ISSUE_LABELS_QUERY)
        if not data or "repository" not in data:
            return []
        return data["repository"].get("labels", {}).get("nodes", [])

    # -- My Contribution --

    def fetch_my_contributions(self, login: str) -> dict[str, Any]:
        """특정 사용자의 이 레포 기여를 가져온다."""
        typer.echo(f"  → contributions by {login}…")
        stats = self.client.rest(f"/repos/{self.owner}/{self.repo}/stats/contributors")
        if not isinstance(stats, list):
            return {}

        for contributor in stats:
            author = contributor.get("author", {})
            if author.get("login", "").lower() == login.lower():
                return contributor
        return {}
