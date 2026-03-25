"""CLI 통합 테스트 — CliRunner + monkeypatched GitHubClient."""

from unittest.mock import patch, MagicMock
import json

from typer.testing import CliRunner

from acta.cli import app

runner = CliRunner()


def _mock_subprocess_run(*args, **kwargs):
    """gh --version 체크를 통과시키는 mock."""
    cmd = args[0] if args else kwargs.get("args", [])
    if cmd == ["gh", "--version"]:
        result = MagicMock()
        result.stdout = "gh version 2.88.1"
        return result
    # GitHubClient 호출 — get_authenticated_user
    if "api" in cmd and "/user" in cmd:
        result = MagicMock()
        result.stdout = json.dumps({"login": "testuser"})
        return result
    # 기타 API 호출 — 빈 응답
    result = MagicMock()
    result.stdout = json.dumps({"data": {"user": {
        "repositories": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []},
        "pullRequests": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []},
        "issues": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []},
        "contributionsCollection": {"pullRequestReviewContributions": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [],
        }},
        "projectsV2": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []},
    }}})
    return result


class TestCliRun:
    @patch("subprocess.run", side_effect=_mock_subprocess_run)
    def test_run_creates_output_directory(self, mock_run, tmp_path):
        """run 후 출력 디렉토리 구조가 생성된다."""
        output = str(tmp_path / "test_data")
        result = runner.invoke(app, ["run", "--days", "7", "--output", output, "--skip-readmes"])

        assert result.exit_code == 0
        assert (tmp_path / "test_data" / "repositories").is_dir()
        assert (tmp_path / "test_data" / "commits").is_dir()
        assert (tmp_path / "test_data" / "issues").is_dir()
        assert (tmp_path / "test_data" / "reviews").is_dir()

    @patch("subprocess.run", side_effect=_mock_subprocess_run)
    def test_run_generates_metadata_and_timeline(self, mock_run, tmp_path):
        """metadata.json과 timeline.csv가 생성된다."""
        output = str(tmp_path / "test_data")
        result = runner.invoke(app, ["run", "--days", "7", "--output", output, "--skip-readmes"])

        assert result.exit_code == 0
        assert (tmp_path / "test_data" / "metadata.json").exists()
        assert (tmp_path / "test_data" / "timeline.csv").exists()
        assert (tmp_path / "test_data" / "SUMMARY.md").exists()

    @patch("subprocess.run", side_effect=_mock_subprocess_run)
    def test_run_with_all_skip_options(self, mock_run, tmp_path):
        """모든 --skip-* 옵션이 정상 동작한다."""
        output = str(tmp_path / "test_data")
        result = runner.invoke(app, [
            "run", "--days", "7", "--output", output,
            "--skip-commits", "--skip-prs", "--skip-readmes",
            "--skip-stars", "--skip-contributed", "--skip-issues", "--skip-reviews",
        ])

        assert result.exit_code == 0
        assert "Done!" in result.output


class TestCliWhoami:
    @patch("subprocess.run", side_effect=_mock_subprocess_run)
    def test_whoami_prints_username(self, mock_run):
        """whoami가 사용자 이름을 출력한다."""
        result = runner.invoke(app, ["whoami"])

        assert result.exit_code == 0
        assert "testuser" in result.output
