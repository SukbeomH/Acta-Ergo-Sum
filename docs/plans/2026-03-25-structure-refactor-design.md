# Acta Ergo Sum — 구조 개선 설계

## 목표

단일 파일(app.py 950줄)을 모듈화하고 테스트 가능한 구조로 개선한다.

## 결정 사항

| 항목 | 선택 |
|---|---|
| 추상화 방식 | GitHubClient 클래스 (OOP) |
| 모듈 분리 | 혼합 (공통 모듈 + extractors 단일 파일) |
| 테스트 프레임워크 | pytest |
| 패키지 관리 | uv |
| 테스트 범위 | 핵심 로직 + 추출기 함수 |

## 모듈 구조

```
acta/
├── __init__.py
├── client.py          # GitHubClient 클래스
├── extractors.py      # extract_* 함수들
├── writers.py         # _write_md, generate_metadata, generate_timeline
├── cli.py             # Typer app
tests/
├── __init__.py
├── test_client.py
├── test_extractors.py
├── test_writers.py
app.py                 # 진입점
pyproject.toml
```

## GitHubClient 설계

```python
class GitHubClient:
    def __init__(self, rate_limit_delay: float = 0.3):
        self.rate_limit_delay = rate_limit_delay

    def rest(self, endpoint: str, **params) -> Any:
        """REST API 호출. 재시도 + rate limit 처리."""

    def graphql(self, query: str, variables: dict) -> Any:
        """GraphQL 호출. 재시도 + error 처리."""

    def get_authenticated_user(self) -> str:
        """현재 인증된 사용자 login 반환."""
```

테스트 시 FakeGitHubClient로 교체:

```python
class FakeGitHubClient(GitHubClient):
    def __init__(self, responses: dict):
        self._responses = responses

    def rest(self, endpoint, **params):
        return self._responses.get(endpoint)

    def graphql(self, query, variables):
        return self._responses.get(self._query_key(query))
```

## 테스트 범위

### test_writers.py — 순수 함수
- `_write_md`: frontmatter 직렬화 (문자열, 리스트, 특수문자)
- `generate_metadata`: JSON 구조, top_languages 계산
- `generate_timeline`: CSV 행 정렬, 필드 매핑

### test_client.py — GitHubClient
- `rest`: 정상 파싱, rate limit 재시도, 실패 시 None
- `graphql`: data 추출, errors 처리
- `get_authenticated_user`: login 반환, 미인증 에러

### test_extractors.py — FakeClient 기반
- `extract_repositories`: GraphQL → MD, 페이지네이션
- `extract_commits`: 작성자 필터링, 월별 그룹핑
- `extract_pull_requests`: since 컷오프, 리뷰 포함
- `extract_readmes`: base64 디코딩, 빈 README 스킵
- `extract_stars`: 월별 그룹핑, 타임스탬프 없는 항목 스킵
- `extract_projects`: 파일명 안전 변환
- `extract_organizations`: 리스트 응답 처리

## 추출기 함수 시그니처 변경

기존: `extract_repositories(base, login, since)` (전역 함수 `_run_gh_graphql` 직접 호출)

변경: `extract_repositories(client, base, login, since)` (GitHubClient 인스턴스 주입)

모든 extract_* 함수에 동일 패턴 적용.
