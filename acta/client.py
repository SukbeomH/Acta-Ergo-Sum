"""GitHub API 클라이언트 — gh CLI를 래핑한다."""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any


class GitHubClient:
    """gh CLI를 통해 GitHub REST/GraphQL API를 호출하는 클라이언트."""

    def __init__(self, rate_limit_delay: float = 0.3):
        self.rate_limit_delay = rate_limit_delay

    def rest(self, endpoint: str, retries: int = 3, delay: float = 5.0, **params: Any) -> Any:
        """REST API 호출. 재시도 + rate limit 처리."""
        cmd = ["gh", "api", endpoint]
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
                )
                if result.stdout.strip():
                    return json.loads(result.stdout)
                return {}
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr or ""
                if "rate limit" in stderr.lower() and attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    return None
            except json.JSONDecodeError:
                return None

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
                )
                data = json.loads(result.stdout)
                if "errors" in data:
                    return None
                return data.get("data")
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr or ""
                if "rate limit" in stderr.lower() and attempt < retries - 1:
                    time.sleep(10 * (attempt + 1))
                else:
                    return None
            except json.JSONDecodeError:
                return None

    def get_authenticated_user(self) -> str:
        """현재 인증된 사용자 login 반환."""
        data = self.rest("/user")
        if not data or "login" not in data:
            raise RuntimeError(
                "Could not retrieve authenticated user. Is `gh auth login` done?"
            )
        return data["login"]
