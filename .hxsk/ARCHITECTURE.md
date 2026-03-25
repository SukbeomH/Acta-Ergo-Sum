# Architecture

## Overview
GitHub 활동 데이터를 수집하여 LLM 친화적 Markdown 지식 베이스로 변환하는 CLI 도구.

## Module Dependency Graph
```
app.py (진입점)
  └── acta/cli.py (Typer CLI)
        ├── acta/client.py (GitHubClient)
        ├── acta/extractors.py (extract_* 함수들)
        │     ├── acta/client.py (DI)
        │     └── acta/writers.py (write_md)
        └── acta/writers.py (generate_metadata, generate_timeline)
```

## Data Flow
```
GitHub API (gh CLI)
  → GitHubClient.rest() / .graphql()
    → extract_* functions (파싱 + 필터링)
      → writers.write_md() (YAML frontmatter + MD)
      → writers.generate_metadata() (JSON)
      → writers.generate_timeline() (CSV)
        → acta_data/ (파일 시스템)
```

## Key Design Decisions
1. **gh CLI 래핑**: 직접 HTTP 대신 gh CLI subprocess — 인증/토큰 관리 위임
2. **DI 패턴**: GitHubClient를 함수에 주입 → FakeGitHubClient로 테스트 격리
3. **혼합 모듈 구조**: 공통 모듈(client, writers) 분리 + extractors 단일 파일 유지
4. **YAML frontmatter**: LLM이 구조화된 메타데이터를 파싱하기 용이

## Boundaries
- **acta/client.py**: 유일한 외부 I/O 지점 (subprocess)
- **acta/extractors.py**: 비즈니스 로직 (API 응답 → 도메인 모델 → 파일)
- **acta/writers.py**: 순수 함수 (데이터 → 파일 포맷)
- **acta/cli.py**: 오케스트레이션 + 사용자 인터페이스
