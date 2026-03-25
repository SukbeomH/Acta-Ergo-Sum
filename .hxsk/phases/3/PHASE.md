# Phase 3: 프로파일링 데이터 보강

## Goal
수집된 데이터의 프로파일링 가치를 높여 LLM이 더 정확하고 설득력 있는 개발자 프로필을 생성할 수 있게 한다.

## Wave Structure

```
Wave 1 (순차 — extractors.py 공유):
  ├── Plan 3.1: 커밋 diff 통계 (additions/deletions)
  ├── Plan 3.2: 레포별 언어 비율
  ├── Plan 3.3: 외부 레포 PR 분리 (writers.py만 — 병렬 가능)
  └── Plan 3.5: Star 레포 상세 정보

Wave 2:
  └── Plan 3.4: 레포 상세 정보 보강 (depends_on: 3.2)
```

## Dependency Graph

```
3.1 ────────────┐
3.2 ──→ 3.4     │
3.3 (독립)      │→ 완료
3.5 ────────────┘
```

> 3.1, 3.2, 3.5는 extractors.py를 수정하므로 순차 실행.
> 3.3은 writers.py만 수정하므로 병렬 가능.

## 보강 효과

| Before | After |
|---|---|
| "2,328 commits" | "+150,000줄 추가 / -30,000줄 삭제" |
| "Python 레포" | "Python 58%, TypeScript 35%, Shell 7%" |
| "217 PRs" | "내 레포 136 PRs + 외부 기여 81 PRs (3개 조직)" |
| star 이름만 | star 설명 + topics + language → 관심 분야 맵 |
| 레포 이름만 | About + 언어 비율 + 활동 지표 → 프로젝트 한눈에 파악 |

## Success Criteria
- [ ] 전체 테스트 통과 (51 + ~5 신규)
- [ ] 커밋에 additions/deletions 포함
- [ ] 레포 MD에 언어 비율 포함
- [ ] SUMMARY.md에 외부 기여 섹션 존재
- [ ] Star/레포 MD body가 풍부한 상세 정보 포함
