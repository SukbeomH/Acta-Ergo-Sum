"""Tests for acta.writers module."""

import csv
import json
from pathlib import Path

from acta.writers import generate_metadata, generate_timeline, write_md


class TestWriteMd:
    def test_basic_frontmatter(self, tmp_path: Path):
        """문자열 값이 포함된 frontmatter를 올바르게 직렬화한다."""
        path = tmp_path / "test.md"
        write_md(path, {"name": "my-repo", "stars": 42}, body="## Hello")

        content = path.read_text()
        assert content.startswith("---\n")
        assert "name: my-repo" in content
        assert "stars: 42" in content
        assert "## Hello" in content

    def test_list_frontmatter(self, tmp_path: Path):
        """리스트 값이 YAML 리스트 형식으로 직렬화된다."""
        path = tmp_path / "test.md"
        write_md(path, {"topics": ["cli", "python"]})

        content = path.read_text()
        assert "topics:" in content
        assert "  - cli" in content
        assert "  - python" in content

    def test_special_characters_in_string(self, tmp_path: Path):
        """따옴표나 개행이 포함된 문자열이 이스케이프된다."""
        path = tmp_path / "test.md"
        write_md(path, {"desc": 'He said "hello"\nworld'})

        content = path.read_text()
        assert "desc:" in content
        # 값이 깨지지 않고 frontmatter 구조가 유지되어야 함
        assert content.count("---") == 2

    def test_creates_parent_directories(self, tmp_path: Path):
        """부모 디렉토리가 없으면 자동 생성한다."""
        path = tmp_path / "sub" / "dir" / "test.md"
        write_md(path, {"key": "value"})

        assert path.exists()

    def test_empty_body(self, tmp_path: Path):
        """body가 비어있으면 frontmatter만 작성한다."""
        path = tmp_path / "test.md"
        write_md(path, {"key": "value"})

        content = path.read_text()
        lines = content.strip().split("\n")
        assert lines[0] == "---"
        assert lines[-1] == "---"


class TestGenerateMetadata:
    def test_writes_metadata_json(self, tmp_path: Path):
        """metadata.json 파일을 생성하고 summary 필드가 올바르다."""
        repos = [
            {"primaryLanguage": {"name": "Python"}},
            {"primaryLanguage": {"name": "Python"}},
            {"primaryLanguage": {"name": "Go"}},
        ]
        meta = generate_metadata(
            base=tmp_path,
            login="testuser",
            days=30,
            repos=repos,
            commits=[{"sha": "abc"}],
            prs=[],
            stars=[{"language": "Rust"}],
            projects=[],
            orgs=[{"login": "org1"}],
            subdirs=["repositories", "commits"],
        )

        assert (tmp_path / "metadata.json").exists()
        data = json.loads((tmp_path / "metadata.json").read_text())
        assert data["github_user"] == "testuser"
        assert data["summary"]["repositories"] == 3
        assert data["summary"]["commits"] == 1
        assert data["summary"]["organizations"] == 1
        assert data["top_languages"]["Python"] == 2
        assert data["top_languages"]["Go"] == 1

    def test_top_starred_languages(self, tmp_path: Path):
        """starred repos의 언어 통계가 올바르다."""
        stars = [
            {"language": "TypeScript"},
            {"language": "TypeScript"},
            {"language": "Rust"},
            {"language": ""},
        ]
        meta = generate_metadata(
            base=tmp_path, login="u", days=7,
            repos=[], commits=[], prs=[], stars=stars,
            projects=[], orgs=[], subdirs=[],
        )
        assert meta["top_starred_languages"]["TypeScript"] == 2
        assert meta["top_starred_languages"]["Rust"] == 1
        assert "" not in meta["top_starred_languages"]


class TestGenerateTimeline:
    def test_writes_sorted_csv(self, tmp_path: Path):
        """timeline.csv가 날짜 역순으로 정렬된다."""
        commits = [
            {"date": "2025-01-15T10:00:00Z", "repo": "repo-a", "message": "fix bug"},
        ]
        prs = [
            {
                "createdAt": "2025-02-01T00:00:00Z",
                "state": "MERGED",
                "title": "Add feature",
                "repository": {"nameWithOwner": "user/repo-b"},
            },
        ]
        stars = [
            {"starred_at": "2025-01-20T00:00:00Z", "name": "cool/lib", "description": "A cool lib"},
        ]

        rows = generate_timeline(tmp_path, commits, prs, stars)

        assert len(rows) == 3
        # 역순: 2025-02-01, 2025-01-20, 2025-01-15
        assert rows[0]["date"] == "2025-02-01"
        assert rows[1]["date"] == "2025-01-20"
        assert rows[2]["date"] == "2025-01-15"

        # CSV 파일 검증
        csv_path = tmp_path / "timeline.csv"
        assert csv_path.exists()
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)
        assert len(csv_rows) == 3
        assert csv_rows[0]["category"] == "PR"
