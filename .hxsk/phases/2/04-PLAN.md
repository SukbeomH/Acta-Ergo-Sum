---
phase: 2
plan: 4
wave: 3
depends_on: [2.1, 2.2, 2.3]
files_modified:
  - acta/writers.py
  - tests/test_writers.py
  - acta/cli.py
autonomous: true
must_haves:
  truths:
    - "SUMMARY.md가 모든 수집 데이터의 LLM 친화적 요약을 포함한다"
    - "활동 통계, 언어 분포, 월별 트렌드가 포함된다"
  artifacts:
    - "acta/writers.py에 generate_summary() 존재"
    - "tests/test_writers.py에 TestGenerateSummary 존재"
    - "acta_data/SUMMARY.md 파일 생성"
---

# Plan 2.4: 요약 리포트 생성

<objective>
수집된 모든 데이터를 기반으로 LLM이 읽기 좋은 SUMMARY.md를 자동 생성한다.

Purpose: metadata.json은 기계 파싱용, SUMMARY.md는 LLM/사람이 한눈에 파악하는 용도
Output: acta_data/SUMMARY.md
</objective>

<context>
Load for context:
- acta/writers.py (generate_metadata — 유사 패턴)
- acta/cli.py (오케스트레이션 끝부분)
</context>

<tasks>

<task type="auto">
  <name>RED: SUMMARY.md 생성 테스트 작성</name>
  <files>tests/test_writers.py</files>
  <action>
    TestGenerateSummary 클래스:
    1. test_writes_summary_md:
       - 모든 수집 결과(repos, commits, prs, issues, reviews, stars, projects, orgs)를 입력
       - SUMMARY.md가 생성되고 다음 섹션 포함 확인:
         - Activity Overview (총 수치)
         - Monthly Activity (월별 커밋/PR/이슈 수)
         - Top Languages (언어 분포)
         - Top Repositories (가장 활발한 레포)
    2. test_handles_empty_data:
       - 모든 입력이 빈 리스트일 때도 정상 생성
  </action>
  <verify>uv run pytest tests/test_writers.py -k "Summary" — RED</verify>
  <done>2개 테스트 ImportError로 실패</done>
</task>

<task type="auto">
  <name>GREEN: generate_summary 구현 + CLI 연동</name>
  <files>acta/writers.py, acta/cli.py</files>
  <action>
    1. writers.py에 generate_summary() 함수:
       - 입력: base, login, days, repos, commits, prs, issues, reviews, stars, projects, orgs
       - 출력: SUMMARY.md (Markdown, frontmatter 없음 — 순수 리포트)
       - 섹션:
         a. # GitHub Activity Summary — {login}
         b. ## Overview (기간, 총 수치 테이블)
         c. ## Monthly Activity (월별 커밋/PR/이슈 카운트 테이블)
         d. ## Top Languages (레포 + star 언어 분포)
         e. ## Most Active Repositories (커밋 수 기준 상위 10개)
         f. ## Recent Pull Requests (최근 10개 PR 요약)
    2. cli.py run()에서 generate_summary 호출 (generate_timeline 다음)

    AVOID: frontmatter 사용하지 않기 — 이 파일은 사람/LLM이 직접 읽는 리포트
  </action>
  <verify>uv run pytest tests/ -v — 전체 GREEN</verify>
  <done>SUMMARY.md가 올바른 섹션 구조로 생성됨</done>
</task>

</tasks>

<verification>
- [ ] uv run pytest tests/ -v — 전체 통과
- [ ] SUMMARY.md에 Overview, Monthly Activity, Top Languages 섹션 존재
- [ ] 빈 데이터에서도 에러 없이 생성
</verification>

<success_criteria>
- [ ] generate_summary 함수 + 2개 테스트 통과
- [ ] CLI run() 실행 시 SUMMARY.md 자동 생성
</success_criteria>
