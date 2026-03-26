---
phase: 3
plan: 3
wave: 1
depends_on: []
files_modified:
  - acta/writers.py
  - tests/test_writers.py
autonomous: true
must_haves:
  truths:
    - "PR이 '내 레포 PR'과 '외부 기여 PR'로 분류된다"
    - "SUMMARY.md에 오픈소스 기여 섹션이 존재한다"
  artifacts:
    - "generate_summary에 외부 기여 PR 섹션 존재"
---

# Plan 3.3: 외부 레포 PR 분리 (오픈소스 기여)

<objective>
현재 PR 데이터에서 `repository.nameWithOwner`가 본인 소유가 아닌 PR을
"오픈소스/외부 기여"로 분류하여 SUMMARY.md에 별도 섹션으로 표시한다.

Purpose: 오픈소스 기여 경험은 이력서에서 높은 가치를 가짐
Output: SUMMARY.md에 "External Contributions" 섹션 추가
</objective>

<context>
- acta/writers.py (generate_summary)
- tests/test_writers.py (TestGenerateSummary)
</context>

<tasks>

<task type="auto">
  <name>RED: 외부 기여 분류 테스트</name>
  <files>tests/test_writers.py</files>
  <action>
    TestGenerateSummary에 테스트 추가:
    - test_separates_external_contributions:
      - login="testuser"인 상태에서 PR 목록에 "testuser/repo"와 "other/repo" PR 혼재
      - SUMMARY.md에 "External Contributions" 섹션 존재
      - "other/repo"가 해당 섹션에 표시
  </action>
  <verify>uv run pytest tests/test_writers.py -k "external" — RED</verify>
  <done>새 테스트 실패</done>
</task>

<task type="auto">
  <name>GREEN: generate_summary에 외부 기여 섹션 추가</name>
  <files>acta/writers.py</files>
  <action>
    1. generate_summary에서 prs를 login 기준으로 분류:
       - own_prs: repository.nameWithOwner가 "{login}/"로 시작
       - external_prs: 나머지
    2. 기존 "Recent Pull Requests" → own PRs만
    3. "## External Contributions" 섹션 추가 — external PRs 표시
       - 레포별 그룹핑, PR 수/상태 표시

    AVOID: extractors 변경 없음 — writers 레벨에서 분류만
  </action>
  <verify>uv run pytest tests/ -v — 전체 GREEN</verify>
  <done>SUMMARY.md에 외부 기여가 분리 표시됨</done>
</task>

</tasks>
