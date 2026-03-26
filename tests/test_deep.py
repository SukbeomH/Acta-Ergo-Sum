"""Tests for acta.deep module — detector, collector, renderer."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

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
    render_my_contribution,
    render_all_sections,
)


# ---------------------------------------------------------------------------
# Detector Tests
# ---------------------------------------------------------------------------


SAMPLE_TREE = [
    "README.md",
    "LICENSE",
    "package.json",
    "tsconfig.json",
    "Dockerfile",
    ".github/workflows/ci.yml",
    "src/index.ts",
    "src/app.ts",
    "src/utils/helper.ts",
    "src/utils/logger.ts",
    "src/components/Button.tsx",
    "src/components/Header.tsx",
    "tests/app.test.ts",
    "docs/README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
]


class TestDetectKeyFiles:
    def test_detects_manifest(self):
        result = detect_key_files(SAMPLE_TREE, category="manifest")
        assert "manifest" in result
        assert "package.json" in result["manifest"]

    def test_detects_ci(self):
        result = detect_key_files(SAMPLE_TREE, category="ci")
        assert "ci" in result
        assert ".github/workflows/ci.yml" in result["ci"]

    def test_detects_docs(self):
        result = detect_key_files(SAMPLE_TREE, category="docs")
        assert "docs" in result
        assert "CONTRIBUTING.md" in result["docs"]
        assert "CHANGELOG.md" in result["docs"]

    def test_detects_all_categories(self):
        result = detect_key_files(SAMPLE_TREE)
        assert "manifest" in result
        assert "infra" in result
        assert "ci" in result
        assert "docs" in result
        assert "config" in result

    def test_empty_tree(self):
        result = detect_key_files([])
        assert result == {}


class TestDetectEntryPoints:
    def test_finds_index_ts(self):
        entries = detect_entry_points(SAMPLE_TREE)
        assert "src/index.ts" in entries

    def test_manifest_hint_takes_priority(self):
        entries = detect_entry_points(SAMPLE_TREE, manifest_hint="src/app.ts")
        assert entries[0] == "src/app.ts"

    def test_skips_deep_paths(self):
        deep_tree = ["a/b/c/d/main.py", "main.py"]
        entries = detect_entry_points(deep_tree)
        assert "main.py" in entries
        assert "a/b/c/d/main.py" not in entries

    def test_skips_non_code_extensions(self):
        tree = ["main.md", "index.json", "app.py"]
        entries = detect_entry_points(tree)
        assert "app.py" in entries
        assert "main.md" not in entries


class TestBuildTreeSummary:
    def test_renders_tree(self):
        tree = build_tree_summary(["src/index.ts", "src/app.ts", "README.md"])
        assert "src/" in tree
        assert "index.ts" in tree
        assert "README.md" in tree

    def test_respects_max_depth(self):
        deep_tree = ["a/b/c/d/e/file.py"]
        tree = build_tree_summary(deep_tree, max_depth=2)
        # depth 2까지만 보여주고 나머지는 축약
        assert "a/" in tree


class TestCountByExtension:
    def test_counts_extensions(self):
        counts = count_by_extension(SAMPLE_TREE)
        assert counts[".ts"] >= 4
        assert counts[".tsx"] == 2
        assert counts[".md"] >= 3

    def test_handles_no_extension(self):
        counts = count_by_extension(["Dockerfile", "Makefile"])
        assert "(no ext)" in counts
        assert counts["(no ext)"] == 2


# ---------------------------------------------------------------------------
# Renderer Tests
# ---------------------------------------------------------------------------


class TestRenderOverview:
    def test_renders_basic_overview(self):
        meta = {
            "nameWithOwner": "user/repo",
            "description": "A cool project",
            "url": "https://github.com/user/repo",
            "createdAt": "2024-01-01T00:00:00Z",
            "pushedAt": "2025-03-01T00:00:00Z",
            "stargazerCount": 100,
            "forkCount": 10,
            "watchers": {"totalCount": 50},
            "issues": {"totalCount": 5},
            "closedIssues": {"totalCount": 20},
            "pullRequests": {"totalCount": 2},
            "mergedPullRequests": {"totalCount": 30},
            "primaryLanguage": {"name": "TypeScript"},
            "licenseInfo": {"name": "MIT License", "spdxId": "MIT", "url": ""},
            "repositoryTopics": {"nodes": [{"topic": {"name": "cli"}}]},
            "isArchived": False,
            "isFork": False,
            "homepageUrl": "https://example.com",
            "parent": None,
            "fundingLinks": [],
            "codeOfConduct": None,
        }

        fm, body = render_overview(meta, "# Hello\n\nThis is README")

        assert fm["name"] == "user/repo"
        assert fm["license"] == "MIT"
        assert "A cool project" in body
        assert "TypeScript" in body
        assert "100" in body
        assert "# Hello" in body


class TestRenderStructure:
    def test_renders_structure(self):
        languages = {"TypeScript": 50000, "CSS": 10000}
        fm, body = render_structure(SAMPLE_TREE, languages)

        assert fm["total_files"] == len(SAMPLE_TREE)
        assert "TypeScript" in body
        assert "Directory Tree" in body
        assert "Key Files" in body


class TestRenderTechStack:
    def test_renders_dependencies(self):
        languages = {"Python": 40000}
        contents = {"pyproject.toml": "[project]\nname = 'test'\n"}
        deps = [{
            "filename": "pyproject.toml",
            "dependenciesCount": 2,
            "dependencies": {"nodes": [
                {"packageName": "typer", "requirements": ">=0.9.0", "hasDependencies": True, "packageManager": "PIP"},
                {"packageName": "pytest", "requirements": ">=8.0", "hasDependencies": True, "packageManager": "PIP"},
            ]},
        }]

        fm, body = render_tech_stack(languages, contents, deps)

        assert "PIP" in fm["dependency_managers"]
        assert "typer" in body
        assert "pytest" in body
        assert "pyproject.toml" in body


class TestRenderEvolution:
    def test_renders_releases_and_commits(self):
        releases = [{
            "name": "v1.0.0",
            "tagName": "v1.0.0",
            "publishedAt": "2025-01-15T00:00:00Z",
            "description": "First stable release",
            "isPrerelease": False,
            "isDraft": False,
        }]
        commits = [{
            "sha": "abc1234567",
            "commit": {
                "message": "feat: add something",
                "author": {"name": "user", "date": "2025-03-01T00:00:00Z"},
            },
            "author": {"login": "user"},
        }]

        fm, body = render_evolution(releases, "## v1.0.0\n- Initial release", commits)

        assert fm["releases_count"] == 1
        assert "v1.0.0" in body
        assert "First stable release" in body
        assert "CHANGELOG" in body
        assert "abc1234" in body

    def test_handles_no_releases(self):
        _, body = render_evolution([], "", [])
        assert "No releases" in body


class TestRenderCommunity:
    def test_renders_health(self):
        health = {
            "health_percentage": 85,
            "files": {
                "readme": {"url": "..."},
                "license": {"url": "..."},
                "contributing": None,
                "code_of_conduct": None,
                "issue_template": None,
                "pull_request_template": {"url": "..."},
            },
        }
        labels = [
            {"name": "bug", "issues": {"totalCount": 15}},
            {"name": "enhancement", "issues": {"totalCount": 8}},
        ]

        fm, body = render_community(health, labels, {})

        assert fm["health_percentage"] == 85
        assert "85%" in body
        assert "README" in body
        assert "bug" in body


class TestRenderMyContribution:
    def test_renders_contribution_stats(self):
        stats = {
            "total": 42,
            "weeks": [
                {"w": 1709510400, "a": 100, "d": 20, "c": 5},
                {"w": 1710115200, "a": 50, "d": 10, "c": 3},
            ],
        }

        fm, body = render_my_contribution(stats, "testuser", "owner/repo")

        assert fm["total_commits"] == 42
        assert fm["total_additions"] == 150
        assert "testuser" in body
        assert "42" in body

    def test_returns_empty_for_no_stats(self):
        fm, body = render_my_contribution({}, "testuser", "owner/repo")
        assert body == ""


class TestRenderAllSections:
    def test_writes_all_files(self, tmp_path: Path):
        sections = render_all_sections(
            base=tmp_path,
            overview={
                "nameWithOwner": "user/repo",
                "description": "Test",
                "url": "",
                "createdAt": "2024-01-01T00:00:00Z",
                "pushedAt": "2025-01-01T00:00:00Z",
                "stargazerCount": 0,
                "forkCount": 0,
                "watchers": {"totalCount": 0},
                "issues": {"totalCount": 0},
                "closedIssues": {"totalCount": 0},
                "pullRequests": {"totalCount": 0},
                "mergedPullRequests": {"totalCount": 0},
                "primaryLanguage": None,
                "licenseInfo": None,
                "repositoryTopics": {"nodes": []},
                "isArchived": False,
                "isFork": False,
                "homepageUrl": "",
                "parent": None,
                "fundingLinks": [],
                "codeOfConduct": None,
            },
            readme="# Test",
            tree_paths=["README.md", "src/main.py"],
            languages={"Python": 1000},
            key_file_contents={},
            dependencies=[],
            releases=[],
            changelog="",
            recent_commits=[],
            health={"health_percentage": 50, "files": {}},
            labels=[],
        )

        assert "overview" in sections
        assert "structure" in sections
        assert "tech_stack" in sections
        assert (tmp_path / "overview.md").exists()
        assert (tmp_path / "structure.md").exists()
        assert (tmp_path / "metadata.json").exists()
