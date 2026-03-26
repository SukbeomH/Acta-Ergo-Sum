# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

See @AGENTS.md for shared project instructions (workflow, memory protocol, validation, agent boundaries).

## Project Overview

**Acta Ergo Sum** — GitHub 활동 데이터를 LLM 친화적 Markdown 지식 베이스로 수집하고, 특정 레포를 딥 분석하여 프로젝트 구조/기술 스택/설계 의도를 추출하는 CLI 도구.

### Document Hierarchy
- **문서 계층**: L1=CLAUDE.md (요약) → L2=skills/SKILL.md (상세) → L3=.hxsk/research/ (출처)

## Commands

```bash
uv run python app.py run --days 365          # 사용자 활동 수집
uv run python app.py deep owner/repo         # 레포 딥 분석
uv run python app.py deep owner/repo --stdout # stdout 출력 (LLM 파이프용)
uv run python app.py mcp                     # MCP 서버 시작
uv run python app.py analyze -t profile      # 템플릿 기반 분석
uv run python app.py whoami                  # 인증 사용자 확인
uv run pytest tests/ -v                      # 테스트 실행 (83개)
uv sync                                      # 의존성 설치
uv sync --extra mcp                          # MCP 포함 설치
uv build                                     # PyPI 패키지 빌드
```

## Architecture

```
acta/
├── client.py              # GitHubClient (gh CLI 래핑, REST/GraphQL)
├── extractors.py          # 13개 extract_* 함수 (client DI)
├── writers.py             # write_md, generate_metadata/timeline/summary
├── cli.py                 # Typer CLI (run, deep, mcp, analyze, whoami)
├── analyzer.py            # 템플릿 기반 프롬프트 빌더
├── mcp_server.py          # FastMCP 서버 (4 tools)
└── deep/
    ├── collector.py       # 레포 딥 분석 데이터 수집
    ├── detector.py        # 핵심 파일/진입점 자동 감지
    └── renderer.py        # 딥 분석 마크다운 렌더링
tests/
├── test_client.py         # GitHubClient 단위 (9)
├── test_extractors.py     # FakeClient 기반 추출기 (30)
├── test_writers.py        # 출력 함수 (10)
├── test_cli.py            # CLI 통합 (6)
├── test_deep.py           # 딥 분석 detector+renderer (22)
└── test_analyzer.py       # 템플릿 로딩/빌드 (6)
app.py                     # 진입점
```

## Extractors (사용자 활동 — `acta run`)

| 함수 | API | 출력 |
|---|---|---|
| `extract_profile` | GraphQL (user) | `profile.md` |
| `extract_pinned_repos` | GraphQL (pinnedItems) | `pinned.md` |
| `extract_contribution_calendar` | GraphQL (contributionCalendar) | `contributions.md` |
| `extract_repositories` | GraphQL (OWNER) | `repositories/*.md` |
| `extract_contributed_repos` | GraphQL (COLLABORATOR/ORG) | `repositories/*.md` |
| `extract_commits` | GraphQL | `commits/YYYY-MM.md` |
| `extract_pull_requests` | GraphQL | `pull_requests/*.md` |
| `extract_issues` | GraphQL | `issues/YYYY-MM.md` |
| `extract_reviews` | GraphQL (contributionsCollection) | `reviews/YYYY-MM.md` |
| `extract_stars` | GraphQL | `stars/YYYY-MM.md` |
| `extract_readmes` | REST | `readmes/*_readme.md` |
| `extract_projects` | GraphQL | `projects/*.md` |
| `extract_organizations` | REST | `organizations/*.md` |

## Deep Analysis (레포 분석 — `acta deep`)

| 섹션 | 데이터 소스 | 출력 |
|---|---|---|
| overview | GraphQL repo + README | `overview.md` |
| structure | Git Tree + Languages | `structure.md` |
| tech_stack | Dependency Graph + 핵심 파일 | `tech_stack.md` |
| evolution | Releases + Commits + CHANGELOG | `evolution.md` |
| community | Community Profile + Labels | `community.md` |
| my_contribution | Stats API | `my_contribution.md` |

## MCP Server (4 tools)

| Tool | 용도 |
|---|---|
| `deep_analyze_repo` | 전체 딥 분석 (섹션 선택 가능) |
| `get_repo_structure` | 디렉토리 트리 + 파일 분포 |
| `get_repo_key_files` | 핵심 설정 파일 내용 |
| `get_repo_evolution` | 릴리스 + 커밋 + CHANGELOG |

## Conventions

- **패키지 관리**: uv (pip/poetry 사용 금지)
- **Python**: 3.12+, `python3` 사용
- **빌드**: hatchling (`uv build`)
- **배포**: PyPI via OIDC trusted publishing (태그 push → 자동 배포)
- **테스트**: pytest, FakeGitHubClient로 subprocess 격리
- **커밋**: conventional commits (feat/fix/refactor/chore)
- **CI**: GitHub Actions (Python 3.12/3.13 매트릭스)

## HXSK

- **Hooks**: `.hxsk/hooks/` — session-start, file-protect, bash-guard, track-modifications, pre-compact-save, stop-context-save
- **Skills**: `.claude/skills/{name}/SKILL.md` — planner, executor, verifier, memory-protocol, commit, handoff
- **Memories**: `.hxsk/memories/` — 파일 기반 A-Mem (17 types)
- **Events**: SessionStart, PreToolUse, PostToolUse, PreCompact, Stop

### Agent Boundaries
- `--dangerously-skip-permissions` 사용 금지
- `.env`, 시크릿 파일 직접 수정 금지
