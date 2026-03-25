"""Tests for acta.client module."""

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from acta.client import GitHubClient


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

    def test_returns_none_on_failure(self):
        """gh 명령 실패 시 None을 반환한다."""
        client = GitHubClient(rate_limit_delay=0)

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "gh", stderr="not found")):
            result = client.rest("/nonexistent")

        assert result is None

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

    def test_returns_none_on_graphql_errors(self):
        """GraphQL errors 필드가 있으면 None을 반환한다."""
        client = GitHubClient(rate_limit_delay=0)
        fake_result = MagicMock()
        fake_result.stdout = json.dumps({
            "errors": [{"message": "Something went wrong"}]
        })

        with patch("subprocess.run", return_value=fake_result):
            result = client.graphql("query { bad }", {})

        assert result is None

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
