# Incremental Update Design

## 제작 의도

Acta Ergo Sum은 GitHub 활동을 주기적으로 수집하여 LLM 지식 베이스를 최신 상태로 유지하는 것이 궁극적 목적이다. 그러나 현재는 매 실행마다 전체 기간을 재수집하므로 API 호출이 불필요하게 많고, 실행 시간이 길다.

**증분 업데이트는 "마지막 실행 이후 변경분만 수집"하여 이 문제를 해결한다.**

## 설계 사상

### 단순함 우선 (Simplicity First)

- 새로운 캐시 시스템이나 상태 DB를 도입하지 않는다
- 이미 존재하는 `metadata.json`의 `generated_at` 필드를 재활용한다
- CLI 레벨에서 `since` 값만 바꾸면 되므로 extractors/writers 변경이 불필요하다

### 멱등성 (Idempotency)

- per-repo 파일 (`repositories/*.md`): 같은 이름으로 덮어쓰므로 자연스럽게 멱등
- 월별 파일 (`commits/YYYY-MM.md`): 해당 월 전체를 재생성 — append가 아닌 replace
- 이 방식이 중복 관리 복잡도를 제거한다

### 무마찰 (Zero Friction)

- 첫 실행인지 증분인지 사용자가 구분할 필요 없음
- `metadata.json`이 없으면 자동으로 `--days` 기본값(365)으로 전체 수집
- 사용자는 항상 같은 명령 (`--since-last-run`)을 실행하면 된다

## 구현 목표

| # | 목표 | 측정 기준 |
|---|---|---|
| 1 | `--since-last-run` 플래그 동작 | 이전 실행 이후 데이터만 수집 |
| 2 | 첫 실행 시 자동 fallback | metadata.json 없이도 정상 동작 |
| 3 | 기존 테스트 깨지지 않음 | 44개 테스트 유지 + 신규 테스트 추가 |
| 4 | extractors/writers 무변경 | CLI 레벨 변경만으로 완성 |

## 상세 설계

### 동작 흐름

```
사용자: uv run python app.py run --since-last-run --output ./acta_data

1. --since-last-run 활성화
2. {output}/metadata.json 읽기 시도
   ├── 존재함 → generated_at 파싱 → since = 해당 타임스탬프
   └── 없음   → since = now - 365일 (fallback), 안내 메시지 출력
3. --days 옵션은 무시됨 (--since-last-run이 우선)
4. 이하 기존 수집 로직 동일 (since 값만 다름)
5. 완료 후 metadata.json 갱신 → 다음 증분의 기준점
```

### 옵션 우선순위

```
--since-last-run (있으면)  →  metadata.json의 generated_at 사용
                          →  metadata.json 없으면 --days fallback
--since-last-run (없으면)  →  --days 값 사용 (기존 동작)
```

### 변경 범위

| 파일 | 변경 내용 |
|---|---|
| `acta/cli.py` | `--since-last-run` 옵션 추가, `since` 계산 분기 로직 |
| `tests/test_cli.py` | 증분 시나리오 2개 테스트 추가 |
| 기타 | 변경 없음 |

### 엣지 케이스

| 상황 | 동작 |
|---|---|
| `metadata.json` 없음 | `--days` 기본값 fallback + 안내 메시지 |
| `metadata.json` 파싱 실패 | 동일 fallback |
| `--since-last-run` + `--days` 동시 지정 | `--since-last-run` 우선 |
| 마지막 실행이 1시간 전 | 1시간분만 수집 (빠름) |
