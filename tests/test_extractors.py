"""Tests for acta.extractors module — FakeGitHubClient 기반."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from acta.client import GitHubClient
from acta.extractors import (
    extract_commits,
    extract_organizations,
    extract_projects,
    extract_pull_requests,
    extract_readmes,
    extract_repositories,
    extract_stars,
)


class FakeGitHubClient(GitHubClient):
    """테스트용 클라이언트 — 미리 정의된 응답을 반환한다."""

    def __init__(
        self,
        rest_responses: dict | None = None,
        graphql_responses: list | None = None,
        rest_sequence: list | None = None,
    ):
        super().__init__(rate_limit_delay=0)
        self._rest_responses = rest_responses or {}
        self._graphql_responses = list(graphql_responses or [])
        self._graphql_call_index = 0
        self._rest_sequence = list(rest_sequence or [])
        self._rest_call_index = 0

    def rest(self, endpoint: str, headers: dict | None = None, **params) -> dict | list | None:
        # rest_sequence가 있으면 순차 반환 (페이지네이션 테스트용)
        if self._rest_sequence and self._rest_call_index < len(self._rest_sequence):
            resp = self._rest_sequence[self._rest_call_index]
            self._rest_call_index += 1
            return resp
        return self._rest_responses.get(endpoint)

    def graphql(self, query: str, variables: dict) -> dict | None:
        if self._graphql_call_index < len(self._graphql_responses):
            resp = self._graphql_responses[self._graphql_call_index]
            self._graphql_call_index += 1
            return resp
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SINCE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _make_repo_node(name: str, language: str = "Python", is_fork: bool = False):
    return {
        "name": name,
        "description": f"Description of {name}",
        "url": f"https://github.com/user/{name}",
        "createdAt": "2025-01-10T00:00:00Z",
        "updatedAt": "2025-02-01T00:00:00Z",
        "pushedAt": "2025-02-01T00:00:00Z",
        "primaryLanguage": {"name": language} if language else None,
        "repositoryTopics": {"nodes": [{"topic": {"name": "cli"}}]},
        "isFork": is_fork,
        "isPrivate": False,
        "stargazerCount": 5,
        "forkCount": 1,
        "defaultBranchRef": {"name": "main"},
    }


# ---------------------------------------------------------------------------
# extract_repositories
# ---------------------------------------------------------------------------


class TestExtractRepositories:
    def test_writes_md_per_repo(self, tmp_path: Path):
        """각 레포마다 하나의 MD 파일을 생성한다."""
        nodes = [_make_repo_node("repo-a"), _make_repo_node("repo-b")]
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"repositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": nodes,
            }}}
        ])

        repos = extract_repositories(client, tmp_path, "user", SINCE)

        assert len(repos) == 2
        assert (tmp_path / "repositories" / "repo-a.md").exists()
        assert (tmp_path / "repositories" / "repo-b.md").exists()

        content = (tmp_path / "repositories" / "repo-a.md").read_text()
        assert "name: repo-a" in content

    def test_handles_pagination(self, tmp_path: Path):
        """여러 페이지를 순회하여 모든 레포를 가져온다."""
        page1 = {"user": {"repositories": {
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
            "nodes": [_make_repo_node("repo-1")],
        }}}
        page2 = {"user": {"repositories": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [_make_repo_node("repo-2")],
        }}}
        client = FakeGitHubClient(graphql_responses=[page1, page2])

        repos = extract_repositories(client, tmp_path, "user", SINCE)
        assert len(repos) == 2


# ---------------------------------------------------------------------------
# extract_commits
# ---------------------------------------------------------------------------


class TestExtractCommits:
    def test_filters_by_author_and_groups_by_month(self, tmp_path: Path):
        """로그인 사용자의 커밋만 필터링하고 월별 파일을 생성한다."""
        repos = [_make_repo_node("my-repo")]
        commit_nodes = [
            {
                "oid": "abc1234567890",
                "message": "fix: something\n\ndetail",
                "committedDate": "2025-01-15T10:00:00Z",
                "author": {"name": "User", "email": "u@e.com", "user": {"login": "testuser"}},
            },
            {
                "oid": "def7890123456",
                "message": "other person commit",
                "committedDate": "2025-01-16T10:00:00Z",
                "author": {"name": "Other", "email": "o@e.com", "user": {"login": "other"}},
            },
        ]
        client = FakeGitHubClient(graphql_responses=[
            {"repository": {"defaultBranchRef": {"target": {"history": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": commit_nodes,
            }}}}}
        ])

        commits = extract_commits(client, tmp_path, "testuser", repos, SINCE)

        assert len(commits) == 1
        assert commits[0]["sha"] == "abc1234"
        assert commits[0]["message"] == "fix: something"

        md_path = tmp_path / "commits" / "2025-01.md"
        assert md_path.exists()
        content = md_path.read_text()
        assert "abc1234" in content

    def test_skips_forks(self, tmp_path: Path):
        """fork 레포는 건너뛴다."""
        repos = [_make_repo_node("forked", is_fork=True)]
        client = FakeGitHubClient(graphql_responses=[])

        commits = extract_commits(client, tmp_path, "user", repos, SINCE)
        assert len(commits) == 0


# ---------------------------------------------------------------------------
# extract_pull_requests
# ---------------------------------------------------------------------------


class TestExtractPullRequests:
    def test_writes_pr_files_with_reviews(self, tmp_path: Path):
        """PR 파일을 생성하고 리뷰 정보를 포함한다."""
        pr_node = {
            "number": 42,
            "title": "Add feature",
            "state": "MERGED",
            "createdAt": "2025-02-01T00:00:00Z",
            "mergedAt": "2025-02-02T00:00:00Z",
            "closedAt": "2025-02-02T00:00:00Z",
            "url": "https://github.com/user/repo/pull/42",
            "body": "This adds a feature.",
            "repository": {"nameWithOwner": "user/repo"},
            "reviews": {"nodes": [
                {"state": "APPROVED", "body": "LGTM", "createdAt": "2025-02-01T12:00:00Z", "author": {"login": "reviewer"}},
            ]},
            "comments": {"nodes": []},
        }
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"pullRequests": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [pr_node],
            }}}
        ])

        prs = extract_pull_requests(client, tmp_path, "user", SINCE)

        assert len(prs) == 1
        md_path = tmp_path / "pull_requests" / "user_repo_pr42.md"
        assert md_path.exists()
        content = md_path.read_text()
        assert "Add feature" in content
        assert "APPROVED" in content

    def test_stops_at_since_cutoff(self, tmp_path: Path):
        """since 이전의 PR은 수집하지 않는다."""
        old_pr = {
            "number": 1,
            "title": "Old PR",
            "state": "CLOSED",
            "createdAt": "2024-06-01T00:00:00Z",
            "mergedAt": None,
            "closedAt": "2024-06-02T00:00:00Z",
            "url": "https://github.com/user/repo/pull/1",
            "body": "",
            "repository": {"nameWithOwner": "user/repo"},
            "reviews": {"nodes": []},
            "comments": {"nodes": []},
        }
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"pullRequests": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [old_pr],
            }}}
        ])

        prs = extract_pull_requests(client, tmp_path, "user", SINCE)
        assert len(prs) == 0


# ---------------------------------------------------------------------------
# extract_readmes
# ---------------------------------------------------------------------------


class TestExtractReadmes:
    def test_decodes_base64_readme(self, tmp_path: Path):
        """base64 인코딩된 README를 디코딩하여 저장한다."""
        import base64
        readme_content = "# My Project\n\nHello world"
        encoded = base64.b64encode(readme_content.encode()).decode()

        repos = [_make_repo_node("my-repo")]
        client = FakeGitHubClient(rest_responses={
            "/repos/user/my-repo/readme": {"content": encoded},
        })

        count = extract_readmes(client, tmp_path, "user", repos)

        assert count == 1
        md_path = tmp_path / "readmes" / "my-repo_readme.md"
        assert md_path.exists()
        content = md_path.read_text()
        assert "# My Project" in content

    def test_skips_empty_readme(self, tmp_path: Path):
        """빈 README는 건너뛴다."""
        import base64
        encoded = base64.b64encode(b"   ").decode()

        repos = [_make_repo_node("empty-repo")]
        client = FakeGitHubClient(rest_responses={
            "/repos/user/empty-repo/readme": {"content": encoded},
        })

        count = extract_readmes(client, tmp_path, "user", repos)
        assert count == 0


# ---------------------------------------------------------------------------
# extract_stars
# ---------------------------------------------------------------------------


class TestExtractStars:
    def test_groups_by_month(self, tmp_path: Path):
        """starred repos를 월별로 그룹핑한다."""
        client = FakeGitHubClient(rest_responses={
            "/users/user/starred": [
                {
                    "starred_at": "2025-02-15T00:00:00Z",
                    "repo": {
                        "full_name": "cool/lib",
                        "description": "A cool library",
                        "html_url": "https://github.com/cool/lib",
                        "language": "Rust",
                        "topics": ["cli"],
                        "stargazers_count": 100,
                    },
                },
                {
                    "starred_at": "2025-01-10T00:00:00Z",
                    "repo": {
                        "full_name": "nice/tool",
                        "description": "A nice tool",
                        "html_url": "https://github.com/nice/tool",
                        "language": "Go",
                        "topics": [],
                        "stargazers_count": 50,
                    },
                },
            ],
        })

        stars = extract_stars(client, tmp_path, "user", SINCE)

        assert len(stars) == 2
        assert (tmp_path / "stars" / "2025-02.md").exists()
        assert (tmp_path / "stars" / "2025-01.md").exists()

    def test_skips_entries_without_timestamp(self, tmp_path: Path):
        """starred_at이 없는 항목은 건너뛴다."""
        client = FakeGitHubClient(rest_responses={
            "/users/user/starred": [
                {"starred_at": "", "repo": {"full_name": "x/y"}},
            ],
        })

        stars = extract_stars(client, tmp_path, "user", SINCE)
        assert len(stars) == 0

    def test_paginates_multiple_pages(self, tmp_path: Path):
        """여러 페이지를 순회하여 모든 starred repos를 수집한다."""
        def _star(name: str, date: str):
            return {
                "starred_at": date,
                "repo": {
                    "full_name": name,
                    "description": f"Desc of {name}",
                    "html_url": f"https://github.com/{name}",
                    "language": "Python",
                    "topics": [],
                    "stargazers_count": 10,
                },
            }

        # 페이지 1: per_page개 (꽉 참 → 다음 페이지 있음)
        # 페이지 2: per_page 미만 (마지막 페이지)
        page1 = [_star("a/repo1", "2025-03-01T00:00:00Z")]
        page2 = [_star("b/repo2", "2025-02-01T00:00:00Z")]

        client = FakeGitHubClient(rest_sequence=[page1, page2])

        stars = extract_stars(client, tmp_path, "user", SINCE, per_page=1)

        assert len(stars) == 2
        assert stars[0]["name"] == "a/repo1"
        assert stars[1]["name"] == "b/repo2"

    def test_stops_pagination_at_since_cutoff(self, tmp_path: Path):
        """since 이전의 star를 만나면 페이지네이션을 중단한다."""
        page1 = [
            {
                "starred_at": "2025-03-01T00:00:00Z",
                "repo": {"full_name": "new/repo", "description": "", "html_url": "", "language": "Go", "topics": [], "stargazers_count": 5},
            },
            {
                "starred_at": "2024-06-01T00:00:00Z",  # since(2025-01-01) 이전
                "repo": {"full_name": "old/repo", "description": "", "html_url": "", "language": "Go", "topics": [], "stargazers_count": 5},
            },
        ]

        client = FakeGitHubClient(rest_sequence=[page1])

        stars = extract_stars(client, tmp_path, "user", SINCE)

        assert len(stars) == 1
        assert stars[0]["name"] == "new/repo"


# ---------------------------------------------------------------------------
# extract_projects
# ---------------------------------------------------------------------------


class TestExtractProjects:
    def test_writes_project_files(self, tmp_path: Path):
        """프로젝트 파일을 생성하고 파일명에 특수문자를 안전하게 변환한다."""
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"projectsV2": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [{
                    "number": 1,
                    "title": "My Project!",
                    "shortDescription": "A project",
                    "url": "https://github.com/users/user/projects/1",
                    "createdAt": "2025-01-01T00:00:00Z",
                    "updatedAt": "2025-02-01T00:00:00Z",
                    "closed": False,
                    "public": True,
                }],
            }}}
        ])

        projects = extract_projects(client, tmp_path, "user")

        assert len(projects) == 1
        # "My Project!" -> "My_Project_"
        assert (tmp_path / "projects" / "project_1_My_Project_.md").exists()


# ---------------------------------------------------------------------------
# extract_organizations
# ---------------------------------------------------------------------------


class TestExtractOrganizations:
    def test_writes_org_files(self, tmp_path: Path):
        """조직 파일을 생성한다."""
        client = FakeGitHubClient(rest_responses={
            "/user/orgs": [
                {"login": "my-org", "description": "My Organization", "url": "https://api.github.com/orgs/my-org", "repos_url": "https://api.github.com/orgs/my-org/repos"},
            ],
        })

        orgs = extract_organizations(client, tmp_path, "user")

        assert len(orgs) == 1
        assert (tmp_path / "organizations" / "my-org.md").exists()
