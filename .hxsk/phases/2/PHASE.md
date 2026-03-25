# Phase 2: 기능 확장

## Goal
GitHub 활동 수집 범위를 확대하고, 요약 리포트 + CLI 통합 테스트로 완성도를 높인다.

## Wave Structure

```
Wave 1 (병렬 가능):
  ├── Plan 2.1: Contributed Repos 커밋 추출
  └── Plan 2.2: Issues 추출기

Wave 2 (Wave 1 이후):
  └── Plan 2.3: Code Review 활동 추출
       └── depends_on: 2.2 (writers.py generate_timeline 시그니처 확정 후)

Wave 3 (Wave 2 이후):
  ├── Plan 2.4: 요약 리포트 생성 (depends_on: 2.1, 2.2, 2.3)
  └── Plan 2.5: CLI 통합 테스트 (depends_on: 2.1, 2.2, 2.3, 2.4)
```

## Dependency Graph

```
2.1 ─────────────────┐
                     ├──→ 2.4 ──→ 2.5
2.2 ──→ 2.3 ────────┘
```

## File Ownership (충돌 방지)

| Plan | extractors.py | writers.py | cli.py | test_extractors.py | test_writers.py | test_cli.py |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 2.1  | ✓ |   | ✓ | ✓ |   |   |
| 2.2  | ✓ | ✓ | ✓ | ✓ |   |   |
| 2.3  | ✓ | ✓ | ✓ | ✓ |   |   |
| 2.4  |   | ✓ | ✓ |   | ✓ |   |
| 2.5  |   |   | △ |   |   | ✓ |

> Wave 1에서 2.1과 2.2가 extractors.py를 동시에 수정하므로 **순차 실행 권장**.

## Estimated Scope

| Plan | 테스트 추가 | 프로덕션 변경 | 난이도 |
|------|-----------|-------------|--------|
| 2.1  | +2~3 | extract_contributed_repos + CLI 옵션 | 낮음 |
| 2.2  | +3 | extract_issues + timeline/metadata 확장 | 낮음 |
| 2.3  | +2 | extract_reviews + timeline/metadata 확장 | 중간 (GraphQL 구조 상이) |
| 2.4  | +2 | generate_summary | 낮음 |
| 2.5  | +4 | CLI 통합 테스트 (프로덕션 변경 최소) | 중간 (mock 구성) |

## Success Criteria
- [ ] 전체 테스트 통과 (기존 31 + 신규 ~13 = ~44개)
- [ ] 새 추출기 3개 (contributed repos, issues, reviews)
- [ ] SUMMARY.md 자동 생성
- [ ] CLI 통합 테스트 존재
