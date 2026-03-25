# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

**Acta Ergo Sum** — GitHub 활동 데이터를 LLM 친화적 Markdown 지식 베이스로 수집하는 CLI 도구.

## Commands

```bash
# 실행
uv run python app.py run --days 365
uv run python app.py whoami

# 테스트
uv run pytest tests/ -v

# 의존성
uv sync
uv add <package>
```

## Architecture

```
acta/                  # 메인 패키지
├── client.py          # GitHubClient (gh CLI 래핑, REST/GraphQL)
├── extractors.py      # extract_* 함수 (client 주입)
├── writers.py         # write_md, generate_metadata, generate_timeline
└── cli.py             # Typer CLI (run, whoami)
tests/                 # pytest 테스트
app.py                 # 진입점
```

## Conventions

- **패키지 관리**: uv (pip/poetry 사용 금지)
- **Python**: 3.12+, `python3` 사용
- **테스트**: pytest, FakeGitHubClient로 subprocess 격리
- **커밋**: conventional commits (feat/fix/refactor/chore)

## HXSK

- **Hook System**: `.hxsk/hooks/` (settings.json에서 참조)
- **Skills**: `.claude/skills/{name}/SKILL.md`
- **Memories**: `.hxsk/memories/` (파일 기반 A-Mem)
- **Events**: SessionStart, PreToolUse, PostToolUse, PreCompact, Stop

### Compaction Rules
압축 시 보존:
- `.hxsk/.track-modifications.log` 변경 파일 목록
- 활성 태스크 컨텍스트
- 메모리 검색 결과

### Agent Boundaries
- `--dangerously-skip-permissions` 사용 금지
- `.env`, 시크릿 파일 직접 수정 금지
