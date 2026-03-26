# Acta Ergo Sum

> *I act, therefore I am.* — GitHub 활동 데이터를 마크다운 지식 베이스로 구조화하고, 레포를 딥 분석하는 CLI 도구.

## Commands

```bash
uv sync                                      # Install deps
uv sync --extra mcp                          # Install with MCP support
uv run python app.py run                     # Collect last 365 days
uv run python app.py run --days 90           # Custom period
uv run python app.py run --days 30 --skip-readmes  # Quick run
uv run python app.py deep owner/repo         # Deep-analyze a repo
uv run python app.py deep owner/repo --stdout # Pipe to LLM agent
uv run python app.py mcp                     # Start MCP server
uv run python app.py analyze -t profile      # Template-based analysis
uv run python app.py whoami                  # Show authenticated user
uv run pytest tests/ -v                      # Run tests (83)
uv build                                     # Build for PyPI
```

## Architecture

```
acta/
├── client.py              # GitHubClient (gh CLI wrapping, REST/GraphQL)
├── extractors.py          # 13 extract_* functions (DI-based)
├── writers.py             # MD/JSON/CSV/Summary output
├── cli.py                 # Typer CLI (run, deep, mcp, analyze, whoami)
├── analyzer.py            # Template-based prompt builder
├── mcp_server.py          # FastMCP server (4 tools)
└── deep/
    ├── collector.py       # Repo deep analysis data collection
    ├── detector.py        # Key file / entry point auto-detection
    └── renderer.py        # Deep analysis markdown rendering
app.py                     # Entry point
```

- **Tech Stack**: Python 3.12+, Typer, GitHub CLI (`gh`), hatchling (build), FastMCP (optional)
- **gh 호출**: `GitHubClient.rest()` / `.graphql()` — retry + rate-limit back-off
- **출력**: YAML Frontmatter 마크다운 + `metadata.json` + `timeline.csv`
- **배포**: PyPI (`acta-ergo-sum`), uvx/pipx/pip 지원

## Key Conventions

- `uv` 기반 패키지 관리 (pip/poetry 사용 금지)
- `gh` CLI 인증 필수 (`gh auth login`)
- 모듈 구조: `acta/` 패키지 + `acta/deep/` 서브패키지
- 테스트: `FakeGitHubClient`로 subprocess 격리
- 빌드: `uv build` → hatchling
- CI/CD: GitHub Actions (test matrix 3.12/3.13, PyPI OIDC publish on tag)

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
- Architectural decisions affecting 3+ functions

### Never
- Read/print .env or credential files
- Commit hardcoded secrets or API keys
- Skip failing tests to "fix later"
