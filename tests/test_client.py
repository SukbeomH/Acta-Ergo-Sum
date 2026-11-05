"""Tests for acta.client module."""

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from acta.client import GitHubClient, GitHubAPIError


class TestRest:
    def test_parses_json_response(self):
        """정상 JSON 응답을 파싱하여 반환한다."""
        client = GitHubClient(rate_limit_delay=0)
        fake_result = MagicMock()
        fake_result.stdout = json.dumps({"login": "testuser"})

        with patch("subprocess.run", return_value=fake_result) as mock_run:
            result = client.rest("/user")

        assert result == {"login": "testuser"}
        mock_run.assert_called_once()

    def test_raises_on_failure(self):
        """A failed request must not masquerade as an empty result."""
        client = GitHubClient(rate_limit_delay=0)

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "gh", stderr="not found")):
            with pytest.raises(GitHubAPIError, match="not found"):
                client.rest("/nonexistent")

    def test_retries_on_rate_limit(self):
        """rate limit 에러 시 재시도한다."""
        client = GitHubClient(rate_limit_delay=0)

        rate_limit_error = subprocess.CalledProcessError(1, "gh", stderr="API rate limit exceeded")
        success_result = MagicMock()
        success_result.stdout = json.dumps({"ok": True})

        with patch("subprocess.run", side_effect=[rate_limit_error, success_result]):
            result = client.rest("/user")

        assert result == {"ok": True}

    def test_returns_empty_dict_for_empty_stdout(self):
        """빈 stdout이면 빈 dict를 반환한다."""
        client = GitHubClient(rate_limit_delay=0)
        fake_result = MagicMock()
        fake_result.stdout = "   "

        with patch("subprocess.run", return_value=fake_result):
            result = client.rest("/user")

        assert result == {}


class TestGraphql:
    def test_returns_data_field(self):
        """GraphQL 응답에서 data 필드를 추출한다."""
        client = GitHubClient(rate_limit_delay=0)
        fake_result = MagicMock()
        fake_result.stdout = json.dumps({
            "data": {"user": {"login": "testuser"}}
        })

        with patch("subprocess.run", return_value=fake_result):
            result = client.graphql("query { user { login } }", {})

        assert result == {"user": {"login": "testuser"}}

    def test_raises_on_graphql_errors(self):
        """Even partial GraphQL errors invalidate the collection checkpoint."""
        client = GitHubClient(rate_limit_delay=0)
        fake_result = MagicMock()
        fake_result.stdout = json.dumps({
            "errors": [{"message": "Something went wrong"}]
        })

        with patch("subprocess.run", return_value=fake_result):
            with pytest.raises(GitHubAPIError, match="Something went wrong"):
                client.graphql("query { bad }", {})

    def test_passes_variables_correctly(self):
        """변수를 올바른 gh CLI 플래그로 변환한다."""
        client = GitHubClient(rate_limit_delay=0)
        fake_result = MagicMock()
        fake_result.stdout = json.dumps({"data": {}})

        with patch("subprocess.run", return_value=fake_result) as mock_run:
            client.graphql("query", {"login": "user", "count": 10, "active": True})

        cmd = mock_run.call_args[0][0]
        # 문자열 변수는 -f, 숫자는 -F, bool은 -F
        assert "-f" in cmd
        assert "login=user" in cmd
        assert "-F" in cmd
        assert "count=10" in cmd
        assert "active=true" in cmd


class TestGetAuthenticatedUser:
    def test_returns_login(self):
        """인증된 사용자의 login을 반환한다."""
        client = GitHubClient(rate_limit_delay=0)
        fake_result = MagicMock()
        fake_result.stdout = json.dumps({"login": "myuser"})

        with patch("subprocess.run", return_value=fake_result):
            assert client.get_authenticated_user() == "myuser"

    def test_raises_on_missing_login(self):
        """login이 없으면 RuntimeError를 발생시킨다."""
        client = GitHubClient(rate_limit_delay=0)
        fake_result = MagicMock()
        fake_result.stdout = json.dumps({})

        with patch("subprocess.run", return_value=fake_result):
            with pytest.raises(RuntimeError):
                client.get_authenticated_user()


@pytest.mark.parametrize("status", [401, 403, 503])
def test_optional_resource_only_tolerates_not_found(status):
    error = subprocess.CalledProcessError(1, "gh", stderr=f"failure (HTTP {status})")
    with patch("subprocess.run", side_effect=error):
        with pytest.raises(GitHubAPIError):
            GitHubClient().rest("/repos/a/b/readme", allow_missing=True)


def test_expected_optional_404_is_not_a_collection_failure():
    error = subprocess.CalledProcessError(1, "gh", stderr="Not Found (HTTP 404)")
    with patch("subprocess.run", side_effect=error):
        assert GitHubClient().rest("/repos/a/b/readme", allow_missing=True) is None
        with pytest.raises(GitHubAPIError):
            GitHubClient().rest("/repos/a/b/readme")


@pytest.mark.parametrize("method", ["rest", "graphql"])
def test_timeouts_are_explicit_failures(method):
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 60)):
        with pytest.raises(GitHubAPIError, match="timed out"):
            client = GitHubClient()
            client.rest("/user") if method == "rest" else client.graphql("query", {})


def test_rest_query_parameters_still_use_get():
    result = MagicMock(stdout='[]')
    with patch("subprocess.run", return_value=result) as run:
        GitHubClient().rest("/user/orgs", per_page=100)
    assert run.call_args.args[0][2:4] == ["--method", "GET"]
