# Acta Ergo Sum

> *I act, therefore I am.* — GitHub 활동 데이터를 마크다운 지식 베이스로 구조화하는 CLI 도구.

## Commands

```bash
pip install -r requirements.txt       # Install deps
python app.py run                     # Collect last 365 days
python app.py run --days 90           # Custom period
python app.py run --days 30 --skip-readmes  # Quick run
python app.py whoami                  # Show authenticated user
```

## Architecture

```
app.py (단일 파일, Typer CLI)
 └─ run()
     ├─ extract_repositories()   → repositories/*.md
     ├─ extract_commits()        → commits/YYYY-MM.md
     ├─ extract_pull_requests()  → pull_requests/*.md
     ├─ extract_readmes()        → readmes/*_readme.md
     ├─ extract_stars()          → stars/YYYY-MM.md
     ├─ extract_projects()       → projects/*.md
     ├─ extract_organizations()  → organizations/*.md
     ├─ generate_metadata()      → metadata.json
     └─ generate_timeline()      → timeline.csv
```

- **Tech Stack**: Python 3.12+, Typer, GitHub CLI (`gh`)
- **gh 호출**: `_run_gh()` / `_run_gh_graphql()` — pagination + rate-limit back-off 자동 처리
- **출력**: YAML Frontmatter 마크다운 + `metadata.json` + `timeline.csv`

## Key Conventions

- 단일 파일 구조 (`app.py`) — 모듈 분리 시 Ask First
- `gh` CLI 인증 필수 (`gh auth login`)
- 출력 디렉토리 기본값: `./acta_data`

---

## HXSK Workflow

SPEC.md → PLAN.md → EXECUTE → VERIFY. Working docs in `.hxsk/`

## Memory Protocol

파일 기반 메모리 시스템 (A-Mem 확장).

| 방식 | 용도 |
|------|------|
| `bash .hxsk/hooks/md-recall-memory.sh <query>` | 훅 기반 검색 (2-hop 지원) |
| 파일 검색: `.hxsk/memories/` | Broad context |
| 타입별 필터: `.hxsk/memories/{type}/*.md` | Narrow filter |

## Validation

검증은 경험적 증거 기반.

- **결과 우선**: 기능 동작 확인 후 스타일 수정
- **실패 전수 보고**: 모든 실패를 수집하여 보고
- **조건부 성공**: 실제 결과 확인 후에만 성공 출력

## Execution Constraints

- **3-Strike Rule**: 동일 접근 3회 연속 실패 시 반드시 전환
- **Atomic Commit**: 태스크당 하나의 커밋. 논리적 단위 유지

## Agent Boundaries

### Always
- 파일 검색 기반 impact analysis before refactoring or deleting code
- 경험적으로 검증 — 명령 실행 결과로 증명

### Ask First
- Adding external dependencies
- `app.py` 단일 파일에서 모듈 분리
- Architectural decisions affecting 3+ functions

### Never
- Read/print .env or credential files
- Commit hardcoded secrets or API keys
- Skip failing tests to "fix later"
