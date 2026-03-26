"""Tests for acta.analyzer module."""

import json
from pathlib import Path

from acta.analyzer import build_prompt, load_template, list_templates


class TestLoadTemplate:
    def test_parses_frontmatter_and_body(self, tmp_path: Path):
        """YAML frontmatter와 프롬프트 본문을 분리하여 파싱한다."""
        tmpl = tmp_path / "test.md"
        tmpl.write_text(
            "---\n"
            "name: test\n"
            "description: A test template\n"
            "context:\n"
            "  - SUMMARY.md\n"
            "  - metadata.json\n"
            "max_tokens: 2048\n"
            "---\n"
            "\n"
            "Analyze this:\n"
            "\n"
            "{{context}}\n"
        )

        meta, body = load_template(tmpl)

        assert meta["name"] == "test"
        assert meta["context"] == ["SUMMARY.md", "metadata.json"]
        assert meta["max_tokens"] == 2048
        assert "{{context}}" in body
        assert "Analyze this:" in body

    def test_handles_missing_optional_fields(self, tmp_path: Path):
        """max_tokens 등 옵션 필드가 없어도 정상 파싱한다."""
        tmpl = tmp_path / "minimal.md"
        tmpl.write_text(
            "---\n"
            "name: minimal\n"
            "context:\n"
            "  - SUMMARY.md\n"
            "---\n"
            "\n"
            "Just do it.\n"
        )

        meta, body = load_template(tmpl)
        assert meta["name"] == "minimal"
        assert meta.get("max_tokens") is None
        assert "Just do it." in body


class TestBuildPrompt:
    def test_substitutes_context(self, tmp_path: Path):
        """{{context}} 자리에 파일 내용이 삽입된다."""
        # 데이터 디렉토리 구성
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "SUMMARY.md").write_text("# Summary\nTotal commits: 100\n")
        (data_dir / "metadata.json").write_text(json.dumps({"user": "test"}))

        template_body = "Analyze:\n\n{{context}}\n\nBe concise."
        context_files = ["SUMMARY.md", "metadata.json"]

        prompt = build_prompt(template_body, context_files, data_dir)

        assert "# Summary" in prompt
        assert "Total commits: 100" in prompt
        assert '"user": "test"' in prompt
        assert "Be concise." in prompt
        assert "{{context}}" not in prompt

    def test_skips_missing_files(self, tmp_path: Path):
        """존재하지 않는 context 파일은 건너뛴다."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "SUMMARY.md").write_text("# Summary\n")

        prompt = build_prompt(
            "{{context}}", ["SUMMARY.md", "nonexistent.md"], data_dir
        )

        assert "# Summary" in prompt
        assert "nonexistent" not in prompt

    def test_glob_pattern_in_context(self, tmp_path: Path):
        """context에 glob 패턴(repositories/*.md)을 사용할 수 있다."""
        data_dir = tmp_path / "data"
        repos_dir = data_dir / "repositories"
        repos_dir.mkdir(parents=True)
        (repos_dir / "repo-a.md").write_text("# repo-a\n")
        (repos_dir / "repo-b.md").write_text("# repo-b\n")

        prompt = build_prompt("{{context}}", ["repositories/*.md"], data_dir)

        assert "# repo-a" in prompt
        assert "# repo-b" in prompt


class TestListTemplates:
    def test_lists_available_templates(self, tmp_path: Path):
        """templates 디렉토리의 .md 파일 목록을 반환한다."""
        (tmp_path / "profile.md").write_text("---\nname: profile\ncontext: []\n---\n")
        (tmp_path / "weekly.md").write_text("---\nname: weekly\ncontext: []\n---\n")
        (tmp_path / "not_a_template.txt").write_text("ignore me")

        names = list_templates(tmp_path)

        assert "profile" in names
        assert "weekly" in names
        assert "not_a_template" not in names
