# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

See @AGENTS.md for shared project instructions (workflow, memory protocol, validation, agent boundaries).

## Project Overview

**Acta Ergo Sum** — GitHub 활동 데이터를 LLM 친화적 Markdown 지식 베이스로 수집하는 CLI 도구.

### Document Hierarchy
- **문서 계층**: L1=CLAUDE.md (요약) → L2=skills/SKILL.md (상세) → L3=.hxsk/research/ (출처)

## Commands

```bash
uv run python app.py run --days 365    # 데이터 수집
uv run python app.py whoami            # 인증 사용자 확인
uv run pytest tests/ -v                # 테스트 실행
uv sync                                # 의존성 설치
uv add <package>                       # 패키지 추가
```

## Architecture

```
acta/
├── client.py          # GitHubClient (gh CLI 래핑, REST/GraphQL)
├── extractors.py      # 10개 extract_* 함수 (client DI)
├── writers.py         # write_md, generate_metadata/timeline/summary
└── cli.py             # Typer CLI (run, whoami)
tests/
├── test_client.py     # GitHubClient 단위 (9)
├── test_extractors.py # FakeClient 기반 추출기 (20)
├── test_writers.py    # 출력 함수 (10)
└── test_cli.py        # CLI 통합 (4)
app.py                 # 진입점
```

## Extractors

| 함수 | API | 출력 |
|---|---|---|
| `extract_repositories` | GraphQL (OWNER) | `repositories/*.md` |
| `extract_contributed_repos` | GraphQL (COLLABORATOR/ORG) | `repositories/*.md` |
| `extract_commits` | GraphQL | `commits/YYYY-MM.md` |
| `extract_pull_requests` | GraphQL | `pull_requests/*.md` |
| `extract_issues` | GraphQL | `issues/YYYY-MM.md` |
| `extract_reviews` | GraphQL (contributionsCollection) | `reviews/YYYY-MM.md` |
| `extract_stars` | REST (paginated) | `stars/YYYY-MM.md` |
| `extract_readmes` | REST | `readmes/*_readme.md` |
| `extract_projects` | GraphQL | `projects/*.md` |
| `extract_organizations` | REST | `organizations/*.md` |
| `extract_profile` | GraphQL | `profile.md` |
| `extract_pinned_repos` | GraphQL | `pinned.md` |
| `extract_contribution_calendar` | GraphQL | `contributions.md` |

## Conventions

- **패키지 관리**: uv (pip/poetry 사용 금지)
- **Python**: 3.12+, `python3` 사용
- **테스트**: pytest, FakeGitHubClient로 subprocess 격리
- **커밋**: conventional commits (feat/fix/refactor/chore)

## HXSK

- **Hooks**: `.hxsk/hooks/` — session-start, file-protect, bash-guard, track-modifications, pre-compact-save, stop-context-save
- **Skills**: `.claude/skills/{name}/SKILL.md` — planner, executor, verifier, memory-protocol, commit, handoff
- **Memories**: `.hxsk/memories/` — 파일 기반 A-Mem (17 types)
- **Events**: SessionStart, PreToolUse, PostToolUse, PreCompact, Stop

### Agent Boundaries
- `--dangerously-skip-permissions` 사용 금지
- `.env`, 시크릿 파일 직접 수정 금지
