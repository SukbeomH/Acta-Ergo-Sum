# LLM Analysis Pipeline Design

## 제작 의도

Acta Ergo Sum은 GitHub 활동을 "LLM 친화적 지식 베이스"로 수집하는 도구다. 그러나 수집 자체는 원재료일 뿐이다. **수집된 데이터를 LLM에 넘겨 실질적 가치(기술 프로필, 주간 리포트, 이력서)로 변환하는 것이 이 기능의 목적이다.**

## 설계 사상

### 프롬프트 파일 우선 (Prompt-First)

- API 호출은 선택 사항이다. 기본 동작은 "프롬프트 파일 생성"까지만
- 사용자가 프롬프트를 확인/수정한 후 실행할 수 있다
- API 키 없이도 핵심 기능을 사용할 수 있다

### 템플릿 외부화 (Templates as Files)

- 프롬프트 템플릿은 코드가 아닌 `templates/*.md` 파일
- 사용자가 직접 편집/추가 가능
- YAML frontmatter로 메타데이터(필요 context, max_tokens) 관리

### 점진적 복잡도 (Progressive Complexity)

```
Level 1: uv run python app.py analyze --template profile
         → analysis/profile.prompt.md 생성 (프롬프트만)

Level 2: uv run python app.py analyze --template profile --call-api
         → analysis/profile.result.md 생성 (Claude API 호출)
```

## 구현 목표

| # | 목표 | 측정 기준 |
|---|---|---|
| 1 | `analyze` CLI 커맨드 동작 | `--template` 지정 시 프롬프트 파일 생성 |
| 2 | 3개 기본 템플릿 제공 | profile, weekly, resume |
| 3 | `--call-api` 시 Claude 호출 | ANTHROPIC_API_KEY로 결과 저장 |
| 4 | API 없이도 사용 가능 | `anthropic` 미설치 시에도 프롬프트 생성 동작 |

## 상세 설계

### 동작 흐름

```
1. --template {name} 파싱
2. templates/{name}.md 로드 (YAML frontmatter + 프롬프트)
3. frontmatter.context 파일들을 {input} 디렉토리에서 로드
4. {{context}} 치환 → 완성된 프롬프트
5. analysis/{name}.prompt.md 저장
6. --call-api 시:
   a. anthropic SDK import (없으면 에러 메시지)
   b. Claude API 호출 (model, max_tokens from frontmatter)
   c. analysis/{name}.result.md 저장
```

### 파일 구조

```
templates/
├── profile.md          # 기술 프로필 템플릿
├── weekly.md           # 주간/월간 리포트 템플릿
└── resume.md           # 이력서 초안 템플릿

acta_data/analysis/     # 출력 (런타임 생성)
├── profile.prompt.md   # 조합된 프롬프트
└── profile.result.md   # Claude API 응답 (--call-api 시)
```

### 변경 범위

| 파일 | 변경 내용 |
|---|---|
| `acta/analyzer.py` | 신규 — 데이터 로딩, 프롬프트 조합, API 호출 |
| `acta/cli.py` | `analyze` 커맨드 추가 |
| `templates/*.md` | 신규 — 3개 프롬프트 템플릿 |
| `tests/test_analyzer.py` | 신규 — 프롬프트 조합 + 템플릿 파싱 테스트 |
| `pyproject.toml` | `anthropic` optional dependency 추가 |

### 템플릿 형식

```markdown
---
name: profile
description: 기술 프로필 생성
context:
  - SUMMARY.md
  - metadata.json
max_tokens: 4096
---

{프롬프트 본문}

## Data

{{context}}

## Instructions

{지시사항}
```

- `context`: 로드할 파일 목록 (input 디렉토리 기준)
- `{{context}}`: 파일 내용이 치환되는 위치
- `max_tokens`: API 호출 시 사용
