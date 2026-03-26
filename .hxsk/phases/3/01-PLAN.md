---
phase: 3
plan: 1
wave: 1
depends_on: []
files_modified:
  - acta/extractors.py
  - tests/test_extractors.py
autonomous: true
must_haves:
  truths:
    - "각 커밋에 additions/deletions 수치가 포함된다"
    - "commits/YYYY-MM.md에 총 추가/삭제 줄 수가 표시된다"
    - "SUMMARY.md에서 '총 N줄 추가' 같은 정량 데이터를 도출할 수 있다"
  artifacts:
    - "커밋 dict에 additions, deletions 필드 존재"
---

# Plan 3.1: 커밋 diff 통계 (additions/deletions)

<objective>
커밋별 코드 변경량(추가/삭제 줄 수)을 수집한다.
"2,328 commits"보다 "+150,000줄 기여"가 프로파일링에서 훨씬 강력한 정량 지표다.

Purpose: 코드 기여 규모 정량화
Output: 커밋 dict에 additions/deletions 추가, 월별 MD에 합산 표시
</objective>

<context>
- acta/extractors.py (extract_commits, _COMMIT_QUERY)
- tests/test_extractors.py (TestExtractCommits)
</context>

<tasks>

<task type="auto">
  <name>RED: 커밋 diff 통계 테스트</name>
  <files>tests/test_extractors.py</files>
  <action>
    TestExtractCommits에 테스트 추가:
    - test_includes_additions_deletions: 커밋 dict에 additions/deletions 포함 확인
    - 월별 MD에 총 additions/deletions 합산 표시 확인

    GraphQL 응답 mock에 additions, deletions 필드 추가.
  </action>
  <verify>uv run pytest tests/test_extractors.py -k "additions" — RED</verify>
  <done>새 테스트 실패</done>
</task>

<task type="auto">
  <name>GREEN: _COMMIT_QUERY에 additions/deletions 추가</name>
  <files>acta/extractors.py</files>
  <action>
    1. _COMMIT_QUERY GraphQL에 additions, deletions 필드 추가:
       ```
       history(first:100, after:$after, since:$since) {
         nodes {
           oid message committedDate
           additions deletions
           author { ... }
         }
       }
       ```
    2. extract_commits의 entry dict에 additions, deletions 추가
    3. 월별 MD 하단에 "Total: +{sum_additions} / -{sum_deletions}" 추가

    AVOID: changedFiles 필드는 GraphQL commit에서 지원 안 됨. additions/deletions만 사용.
  </action>
  <verify>uv run pytest tests/ -v — 전체 GREEN</verify>
  <done>커밋에 additions/deletions 포함, 월별 합산 표시</done>
</task>

</tasks>
