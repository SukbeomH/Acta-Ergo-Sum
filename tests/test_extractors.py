"""Tests for acta.extractors module — FakeGitHubClient 기반."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

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
        # 정확한 키 매칭
        if endpoint in self._rest_responses:
            return self._rest_responses[endpoint]
        # 접두사 매칭 (e.g. "/repos/user/" → 모든 /repos/user/* 매칭)
        for key, val in self._rest_responses.items():
            if key.endswith("*") and endpoint.startswith(key[:-1]):
                return val
        return None

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
        # rich body 검증
        assert "**Language**:" in content
        assert "**Stars**:" in content
        assert "Description of repo-a" in content

    def test_includes_language_breakdown(self, tmp_path: Path):
        """repositories/*.md frontmatter에 언어 비율이 포함된다."""
        nodes = [_make_repo_node("my-repo")]
        client = FakeGitHubClient(
            graphql_responses=[
                {"user": {"repositories": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": nodes,
                }}}
            ],
            rest_responses={
                "/repos/user/my-repo/languages": {"Python": 50000, "JavaScript": 30000, "Shell": 5000},
            },
        )

        repos = extract_repositories(client, tmp_path, "user", SINCE)

        content = (tmp_path / "repositories" / "my-repo.md").read_text()
        assert "Python:" in content
        assert "58" in content  # 58.8%
        assert "JavaScript:" in content

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
# extract_contributed_repos
# ---------------------------------------------------------------------------


class TestExtractContributedRepos:
    def test_fetches_collaborator_repos(self, tmp_path: Path):
        """COLLABORATOR/ORG_MEMBER affiliation 레포를 반환한다."""
        nodes = [_make_repo_node("org-project", language="TypeScript")]
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"repositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": nodes,
            }}}
        ])

        repos = extract_contributed_repos(client, tmp_path, "user", SINCE, exclude_names=set())

        assert len(repos) == 1
        assert repos[0]["name"] == "org-project"
        assert (tmp_path / "repositories" / "org-project.md").exists()

    def test_excludes_already_owned_repos(self, tmp_path: Path):
        """이미 OWNER로 수집된 레포를 중복 제외한다."""
        nodes = [
            _make_repo_node("my-repo"),
            _make_repo_node("org-only"),
        ]
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"repositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": nodes,
            }}}
        ])

        repos = extract_contributed_repos(
            client, tmp_path, "user", SINCE, exclude_names={"my-repo"}
        )

        assert len(repos) == 1
        assert repos[0]["name"] == "org-only"


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

    def test_includes_additions_deletions(self, tmp_path: Path):
        """커밋에 additions/deletions가 포함되고 월별 MD에 합산 표시된다."""
        repos = [_make_repo_node("my-repo")]
        commit_nodes = [
            {
                "oid": "aaa1111111111",
                "message": "feat: add feature",
                "committedDate": "2025-02-10T10:00:00Z",
                "additions": 150,
                "deletions": 30,
                "author": {"name": "User", "email": "u@e.com", "user": {"login": "testuser"}},
            },
            {
                "oid": "bbb2222222222",
                "message": "fix: bug",
                "committedDate": "2025-02-15T10:00:00Z",
                "additions": 10,
                "deletions": 5,
                "author": {"name": "User", "email": "u@e.com", "user": {"login": "testuser"}},
            },
        ]
        client = FakeGitHubClient(graphql_responses=[
            {"repository": {"defaultBranchRef": {"target": {"history": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": commit_nodes,
            }}}}}
        ])

        commits = extract_commits(client, tmp_path, "testuser", repos, SINCE)

        assert commits[0]["additions"] == 150
        assert commits[0]["deletions"] == 30
        assert commits[1]["additions"] == 10

        md_path = tmp_path / "commits" / "2025-02.md"
        content = md_path.read_text()
        assert "+160" in content  # 150 + 10
        assert "-35" in content   # 30 + 5

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


def _make_star_edge(name: str, date: str, language: str = "Python", desc: str = ""):
    """GraphQL starredRepositories edge 헬퍼."""
    return {
        "starredAt": date,
        "node": {
            "nameWithOwner": name,
            "description": desc or f"Desc of {name}",
            "url": f"https://github.com/{name}",
            "primaryLanguage": {"name": language} if language else None,
            "stargazerCount": 10,
            "repositoryTopics": {"nodes": []},
        },
    }


class TestExtractStars:
    def test_groups_by_month(self, tmp_path: Path):
        """starred repos를 월별로 그룹핑한다."""
        edges = [
            _make_star_edge("cool/lib", "2025-02-15T00:00:00Z", "Rust"),
            _make_star_edge("nice/tool", "2025-01-10T00:00:00Z", "Go"),
        ]
        client = FakeGitHubClient(graphql_responses=[
            {"viewer": {"starredRepositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "edges": edges,
            }}}
        ])

        stars = extract_stars(client, tmp_path, "user", SINCE)

        assert len(stars) == 2
        assert (tmp_path / "stars" / "2025-02.md").exists()
        assert (tmp_path / "stars" / "2025-01.md").exists()

        # 상세 정보 검증
        content = (tmp_path / "stars" / "2025-02.md").read_text()
        assert "cool/lib" in content
        assert "Rust" in content
        assert "Stars:" in content
        assert "Desc of cool/lib" in content

    def test_paginates_multiple_pages(self, tmp_path: Path):
        """여러 페이지를 순회하여 모든 starred repos를 수집한다."""
        page1 = {"viewer": {"starredRepositories": {
            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
            "edges": [_make_star_edge("a/repo1", "2025-03-01T00:00:00Z")],
        }}}
        page2 = {"viewer": {"starredRepositories": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "edges": [_make_star_edge("b/repo2", "2025-02-01T00:00:00Z")],
        }}}
        client = FakeGitHubClient(graphql_responses=[page1, page2])

        stars = extract_stars(client, tmp_path, "user", SINCE)

        assert len(stars) == 2
        assert stars[0]["name"] == "a/repo1"
        assert stars[1]["name"] == "b/repo2"

    def test_stops_pagination_at_since_cutoff(self, tmp_path: Path):
        """since 이전의 star를 만나면 페이지네이션을 중단한다."""
        edges = [
            _make_star_edge("new/repo", "2025-03-01T00:00:00Z"),
            _make_star_edge("old/repo", "2024-06-01T00:00:00Z"),
        ]
        client = FakeGitHubClient(graphql_responses=[
            {"viewer": {"starredRepositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "edges": edges,
            }}}
        ])

        stars = extract_stars(client, tmp_path, "user", SINCE)

        assert len(stars) == 1
        assert stars[0]["name"] == "new/repo"


# ---------------------------------------------------------------------------
# extract_issues
# ---------------------------------------------------------------------------


class TestExtractIssues:
    def test_writes_issue_files_grouped_by_month(self, tmp_path: Path):
        """이슈를 월별 MD 파일로 그룹핑하여 생성한다."""
        issue_nodes = [
            {
                "number": 10,
                "title": "Bug report",
                "state": "OPEN",
                "createdAt": "2025-02-15T00:00:00Z",
                "closedAt": None,
                "url": "https://github.com/user/repo/issues/10",
                "body": "Something is broken",
                "repository": {"nameWithOwner": "user/repo"},
                "labels": {"nodes": [{"name": "bug"}]},
                "comments": {"nodes": []},
            },
            {
                "number": 11,
                "title": "Feature request",
                "state": "CLOSED",
                "createdAt": "2025-01-05T00:00:00Z",
                "closedAt": "2025-01-20T00:00:00Z",
                "url": "https://github.com/user/repo/issues/11",
                "body": "Please add X",
                "repository": {"nameWithOwner": "user/repo"},
                "labels": {"nodes": [{"name": "enhancement"}]},
                "comments": {"nodes": []},
            },
        ]
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"issues": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": issue_nodes,
            }}}
        ])

        issues = extract_issues(client, tmp_path, "user", SINCE)

        assert len(issues) == 2
        assert (tmp_path / "issues" / "2025-02.md").exists()
        assert (tmp_path / "issues" / "2025-01.md").exists()

        content = (tmp_path / "issues" / "2025-02.md").read_text()
        assert "Bug report" in content
        assert "bug" in content

    def test_stops_at_since_cutoff(self, tmp_path: Path):
        """since 이전의 이슈는 수집하지 않는다."""
        old_issue = {
            "number": 1,
            "title": "Old issue",
            "state": "CLOSED",
            "createdAt": "2024-06-01T00:00:00Z",
            "closedAt": "2024-06-02T00:00:00Z",
            "url": "https://github.com/user/repo/issues/1",
            "body": "",
            "repository": {"nameWithOwner": "user/repo"},
            "labels": {"nodes": []},
            "comments": {"nodes": []},
        }
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"issues": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [old_issue],
            }}}
        ])

        issues = extract_issues(client, tmp_path, "user", SINCE)
        assert len(issues) == 0

    def test_includes_comments_in_body(self, tmp_path: Path):
        """이슈 코멘트가 MD body에 포함된다."""
        issue = {
            "number": 5,
            "title": "Discussion",
            "state": "OPEN",
            "createdAt": "2025-03-01T00:00:00Z",
            "closedAt": None,
            "url": "https://github.com/user/repo/issues/5",
            "body": "Main topic",
            "repository": {"nameWithOwner": "user/repo"},
            "labels": {"nodes": []},
            "comments": {"nodes": [
                {"body": "I agree", "createdAt": "2025-03-02T00:00:00Z", "author": {"login": "commenter"}},
            ]},
        }
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"issues": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [issue],
            }}}
        ])

        issues = extract_issues(client, tmp_path, "user", SINCE)

        content = (tmp_path / "issues" / "2025-03.md").read_text()
        assert "I agree" in content
        assert "commenter" in content


# ---------------------------------------------------------------------------
# extract_reviews
# ---------------------------------------------------------------------------


class TestExtractReviews:
    def test_writes_review_files_grouped_by_month(self, tmp_path: Path):
        """리뷰 활동을 월별 MD 파일로 그룹핑한다."""
        review_nodes = [
            {
                "occurredAt": "2025-02-10T00:00:00Z",
                "pullRequestReview": {
                    "state": "APPROVED",
                    "createdAt": "2025-02-10T00:00:00Z",
                    "body": "LGTM",
                    "pullRequest": {
                        "title": "Add feature X",
                        "number": 42,
                        "url": "https://github.com/other/repo/pull/42",
                        "repository": {"nameWithOwner": "other/repo"},
                    },
                },
            },
        ]
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"contributionsCollection": {
                "pullRequestReviewContributions": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": review_nodes,
                },
            }}}
        ])

        reviews = extract_reviews(client, tmp_path, "user", SINCE)

        assert len(reviews) == 1
        assert (tmp_path / "reviews" / "2025-02.md").exists()
        content = (tmp_path / "reviews" / "2025-02.md").read_text()
        assert "Add feature X" in content
        assert "APPROVED" in content

    def test_stops_at_since_cutoff(self, tmp_path: Path):
        """since 이전의 리뷰는 수집하지 않는다."""
        old_review = {
            "occurredAt": "2024-06-01T00:00:00Z",
            "pullRequestReview": {
                "state": "COMMENTED",
                "createdAt": "2024-06-01T00:00:00Z",
                "body": "old",
                "pullRequest": {
                    "title": "Old PR",
                    "number": 1,
                    "url": "https://github.com/other/repo/pull/1",
                    "repository": {"nameWithOwner": "other/repo"},
                },
            },
        }
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"contributionsCollection": {
                "pullRequestReviewContributions": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [old_review],
                },
            }}}
        ])

        reviews = extract_reviews(client, tmp_path, "user", SINCE)
        assert len(reviews) == 0


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


# ---------------------------------------------------------------------------
# extract_profile
# ---------------------------------------------------------------------------


class TestExtractProfile:
    def test_writes_profile_md(self, tmp_path: Path):
        """프로필 정보를 profile.md에 저장한다."""
        client = FakeGitHubClient(graphql_responses=[
            {"user": {
                "login": "testuser",
                "name": "Test User",
                "bio": "Developer and open source contributor",
                "company": "ACME Corp",
                "location": "Seoul, Korea",
                "websiteUrl": "https://example.com",
                "twitterUsername": "testuser",
                "avatarUrl": "https://avatars.githubusercontent.com/u/123",
                "isHireable": True,
                "createdAt": "2020-01-01T00:00:00Z",
                "updatedAt": "2025-03-01T00:00:00Z",
                "followers": {"totalCount": 100},
                "following": {"totalCount": 50},
                "repositories": {"totalCount": 30},
                "gists": {"totalCount": 5},
                "socialAccounts": {"nodes": [
                    {"provider": "LINKEDIN", "displayName": "testuser", "url": "https://linkedin.com/in/testuser"},
                ]},
                "status": {"message": "Working on Acta", "emoji": ":rocket:"},
            }}
        ])

        profile = extract_profile(client, tmp_path, "testuser")

        assert profile["login"] == "testuser"
        assert (tmp_path / "profile.md").exists()

        content = (tmp_path / "profile.md").read_text()
        assert "Test User" in content
        assert "Seoul, Korea" in content
        assert "ACME Corp" in content
        assert "Hireable" in content
        assert "LINKEDIN" in content
        assert "Working on Acta" in content

    def test_handles_empty_profile(self, tmp_path: Path):
        """API 실패 시 빈 dict를 반환한다."""
        client = FakeGitHubClient(graphql_responses=[None])

        profile = extract_profile(client, tmp_path, "testuser")

        assert profile == {}


# ---------------------------------------------------------------------------
# extract_pinned_repos
# ---------------------------------------------------------------------------


class TestExtractPinnedRepos:
    def test_writes_pinned_md(self, tmp_path: Path):
        """핀된 레포를 pinned.md에 저장한다."""
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"pinnedItems": {"nodes": [
                {
                    "name": "cool-project",
                    "description": "A cool project",
                    "url": "https://github.com/testuser/cool-project",
                    "primaryLanguage": {"name": "Python"},
                    "stargazerCount": 42,
                    "forkCount": 5,
                    "repositoryTopics": {"nodes": [{"topic": {"name": "cli"}}]},
                    "isPrivate": False,
                    "homepageUrl": "https://cool-project.dev",
                },
                {
                    "name": "awesome-lib",
                    "description": "An awesome library",
                    "url": "https://github.com/testuser/awesome-lib",
                    "primaryLanguage": {"name": "TypeScript"},
                    "stargazerCount": 100,
                    "forkCount": 20,
                    "repositoryTopics": {"nodes": []},
                    "isPrivate": False,
                    "homepageUrl": None,
                },
            ]}}}
        ])

        pinned = extract_pinned_repos(client, tmp_path, "testuser")

        assert len(pinned) == 2
        assert pinned[0]["name"] == "cool-project"
        assert pinned[1]["stars"] == 100
        assert (tmp_path / "pinned.md").exists()

        content = (tmp_path / "pinned.md").read_text()
        assert "cool-project" in content
        assert "awesome-lib" in content
        assert "Python" in content
        assert "cool-project.dev" in content

    def test_handles_no_pinned_repos(self, tmp_path: Path):
        """핀된 레포가 없으면 빈 리스트를 반환한다."""
        client = FakeGitHubClient(graphql_responses=[
            {"user": {"pinnedItems": {"nodes": []}}}
        ])

        pinned = extract_pinned_repos(client, tmp_path, "testuser")

        assert pinned == []


# ---------------------------------------------------------------------------
# extract_contribution_calendar
# ---------------------------------------------------------------------------


class TestExtractContributionCalendar:
    def _make_calendar_response(self, daily_counts: list[tuple[str, int]]):
        """테스트용 calendar 응답을 생성한다."""
        weeks = []
        current_week: list[dict] = []
        for i, (date, count) in enumerate(daily_counts):
            weekday = i % 7
            current_week.append({"date": date, "contributionCount": count, "weekday": weekday})
            if weekday == 6:
                weeks.append({"contributionDays": current_week})
                current_week = []
        if current_week:
            weeks.append({"contributionDays": current_week})

        total = sum(c for _, c in daily_counts)
        return {"user": {"contributionsCollection": {
            "contributionCalendar": {
                "totalContributions": total,
                "weeks": weeks,
            },
            "totalCommitContributions": total - 5,
            "totalPullRequestContributions": 3,
            "totalPullRequestReviewContributions": 2,
            "totalIssueContributions": 0,
            "totalRepositoryContributions": 1,
            "restrictedContributionsCount": 10,
        }}}

    def test_writes_contributions_md(self, tmp_path: Path):
        """기여 캘린더를 contributions.md에 저장한다."""
        daily = [
            ("2025-01-01", 5),
            ("2025-01-02", 3),
            ("2025-01-03", 0),
            ("2025-01-04", 7),
            ("2025-01-05", 2),
            ("2025-01-06", 0),
            ("2025-01-07", 1),
        ]
        client = FakeGitHubClient(graphql_responses=[self._make_calendar_response(daily)])

        stats = extract_contribution_calendar(client, tmp_path, "testuser", SINCE)

        assert stats["total_contributions"] == 18
        assert stats["active_days"] == 5
        assert stats["max_daily"] == 7
        assert stats["commits"] == 13
        assert stats["private_contributions"] == 10
        assert (tmp_path / "contributions.md").exists()

        content = (tmp_path / "contributions.md").read_text()
        assert "Total contributions" in content
        assert "18" in content
        assert "Monthly" in content
        assert "Weekday" in content

    def test_calculates_streak(self, tmp_path: Path):
        """연속 기여 일수를 정확히 계산한다."""
        daily = [
            ("2025-01-01", 1),
            ("2025-01-02", 2),
            ("2025-01-03", 3),
            ("2025-01-04", 0),
            ("2025-01-05", 1),
            ("2025-01-06", 1),
            ("2025-01-07", 1),
        ]
        client = FakeGitHubClient(graphql_responses=[self._make_calendar_response(daily)])

        stats = extract_contribution_calendar(client, tmp_path, "testuser", SINCE)

        assert stats["max_streak"] == 3
        assert stats["current_streak"] == 3

    def test_handles_empty_calendar(self, tmp_path: Path):
        """API 실패 시 빈 dict를 반환한다."""
        client = FakeGitHubClient(graphql_responses=[None])

        stats = extract_contribution_calendar(client, tmp_path, "testuser", SINCE)

        assert stats == {}
