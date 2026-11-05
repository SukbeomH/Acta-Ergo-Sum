"""GitHub API 클라이언트 — gh CLI를 래핑한다."""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any


class GitHubAPIError(RuntimeError):
    """A request failed rather than returning an empty collection."""


class GitHubClient:
    """gh CLI를 통해 GitHub REST/GraphQL API를 호출하는 클라이언트."""

    def __init__(self, rate_limit_delay: float = 0.3):
        self.rate_limit_delay = rate_limit_delay

    def rest(
        self, endpoint: str, retries: int = 3, delay: float = 5.0,
        headers: dict[str, str] | None = None, *, allow_missing: bool = False, **params: Any,
    ) -> Any:
        """REST API 호출. 재시도 + rate limit 처리."""
        cmd = ["gh", "api", "--method", "GET", endpoint]
        for name, value in (headers or {}).items():
            cmd += ["--header", f"{name}: {value}"]
        for key, value in params.items():
            cmd += ["-F", f"{key}={value}"]

        for attempt in range(retries):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                    timeout=60,
                )
                if result.stdout.strip():
                    return json.loads(result.stdout)
                return {}
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr or ""
                if "rate limit" in stderr.lower() and attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                elif allow_missing and "HTTP 404" in stderr:
                    return None
                else:
                    raise GitHubAPIError(f"REST request failed: {endpoint}: {stderr.strip()}") from exc
            except (json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
                raise GitHubAPIError(f"Invalid or timed out REST response: {endpoint}") from exc
        raise GitHubAPIError(f"REST retries exhausted: {endpoint}")

    def graphql(self, query: str, variables: dict[str, Any], retries: int = 3) -> Any:
        """GraphQL 호출. 재시도 + error 처리."""
        cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            if isinstance(value, bool):
                cmd += ["-F", f"{key}={str(value).lower()}"]
            elif isinstance(value, int):
                cmd += ["-F", f"{key}={value}"]
            else:
                cmd += ["-f", f"{key}={value}"]

        for attempt in range(retries):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                    timeout=60,
                )
                data = json.loads(result.stdout)
                if data.get("errors") or not isinstance(data.get("data"), dict):
                    raise GitHubAPIError(f"GraphQL request failed: {data.get('errors', 'missing data')}")
                return data["data"]
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr or ""
                if "rate limit" in stderr.lower() and attempt < retries - 1:
                    time.sleep(10 * (attempt + 1))
                else:
                    raise GitHubAPIError(f"GraphQL request failed: {stderr.strip()}") from exc
            except (json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
                raise GitHubAPIError("Invalid or timed out GraphQL response") from exc
        raise GitHubAPIError("GraphQL retries exhausted")

    def get_authenticated_user(self) -> str:
        """현재 인증된 사용자 login 반환."""
        data = self.rest("/user")
        if not data or "login" not in data:
            raise GitHubAPIError(
                "Could not retrieve authenticated user. Is `gh auth login` done?"
            )
        return data["login"]
