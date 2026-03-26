---
phase: 2
plan: 2
wave: 1
depends_on: []
files_modified:
  - acta/extractors.py
  - tests/test_extractors.py
  - acta/writers.py
  - acta/cli.py
autonomous: true
must_haves:
  truths:
    - "사용자가 생성한 이슈와 코멘트가 수집된다"
    - "이슈가 issues/YYYY-MM.md로 월별 그룹핑된다"
    - "timeline.csv에 Issue 카테고리가 포함된다"
  artifacts:
    - "acta/extractors.py에 extract_issues() 존재"
    - "tests/test_extractors.py에 TestExtractIssues 존재"
    - "issues/ 디렉토리에 월별 MD 파일 생성"
---

# Plan 2.2: Issues 추출기

<objective>
사용자가 생성한 GitHub Issues를 수집하여 월별 Markdown 파일로 출력한다.

Purpose: 이슈 작성/코멘트도 핵심 활동 지표이나 현재 미수집
Output: issues/YYYY-MM.md + timeline.csv 확장
</objective>

<context>
Load for context:
- acta/extractors.py (extract_pull_requests 패턴 — 가장 유사한 구조)
- acta/writers.py (generate_timeline)
- acta/cli.py (run 함수 오케스트레이션)
</context>

<tasks>

<task type="auto">
  <name>RED: Issues 추출 테스트 작성</name>
  <files>tests/test_extractors.py</files>
  <action>
    TestExtractIssues 클래스:
    1. test_writes_issue_files_grouped_by_month:
       - GraphQL 응답 → issues/YYYY-MM.md 생성 확인
       - frontmatter에 period, category, total 포함
    2. test_stops_at_since_cutoff:
       - since 이전 이슈는 수집하지 않음
    3. test_includes_comments:
       - 이슈 코멘트가 MD body에 포함

    GraphQL 쿼리 구조:
    user.issues(first:50, orderBy:{UPDATED_AT,DESC}) → number, title, state, createdAt, closedAt, url, body, repository, comments, labels
  </action>
  <verify>uv run pytest tests/test_extractors.py -k "Issues" — RED</verify>
  <done>3개 테스트가 ImportError로 실패</done>
</task>

<task type="auto">
  <name>GREEN: extract_issues 구현 + CLI/timeline 연동</name>
  <files>acta/extractors.py, acta/writers.py, acta/cli.py</files>
  <action>
    1. extractors.py:
       - _ISSUE_QUERY GraphQL 쿼리 (user.issues, pagination)
       - extract_issues(client, base, login, since) → list[dict]
       - 월별 그룹핑 → issues/YYYY-MM.md (commits 패턴 동일)
       - 각 이슈: number, title, state, repo, created, labels, comments 포함
    2. writers.py generate_timeline에 issues 파라미터 추가:
       - Issue 카테고리 행 추가
    3. cli.py:
       - _SUBDIRS에 "issues" 추가
       - run()에 --skip-issues 옵션 + extract_issues 호출
       - generate_timeline/generate_metadata에 issues 전달

    AVOID: PR과 Issue를 같은 파일에 합치지 않기 — 카테고리 분리 유지
  </action>
  <verify>uv run pytest tests/ -v — 전체 GREEN</verify>
  <done>이슈가 월별 MD로 생성되고, timeline.csv에 Issue 행 포함</done>
</task>

</tasks>

<verification>
- [ ] uv run pytest tests/ -v — 전체 통과
- [ ] issues/ 디렉토리에 월별 MD 생성 확인
- [ ] timeline.csv에 Issue 카테고리 행 존재
- [ ] metadata.json summary에 issues 카운트 포함
</verification>

<success_criteria>
- [ ] extract_issues 함수 + 3개 테스트 통과
- [ ] CLI --skip-issues 옵션 동작
- [ ] timeline/metadata에 issues 통합
</success_criteria>
