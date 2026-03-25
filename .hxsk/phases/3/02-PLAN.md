---
phase: 3
plan: 2
wave: 1
depends_on: []
files_modified:
  - acta/extractors.py
  - tests/test_extractors.py
autonomous: true
must_haves:
  truths:
    - "각 레포의 실제 언어 비율(바이트)이 수집된다"
    - "repositories/*.md frontmatter에 languages 필드 존재"
  artifacts:
    - "repositories/*.md에 languages: {Python: 65%, TypeScript: 30%} 포함"
---

# Plan 3.2: 레포별 실제 언어 비율

<objective>
primaryLanguage는 레포의 "주요 언어" 1개만 표시한다. 실제로는 여러 언어가 혼재하므로
REST `/repos/{owner}/{repo}/languages` API로 바이트 단위 비율을 수집한다.

Purpose: "Python 레포라도 80%가 JS"인 경우를 정확히 파악
Output: repositories/*.md에 languages 필드 추가
</objective>

<context>
- acta/extractors.py (extract_repositories — MD 작성 부분)
- acta/client.py (GitHubClient.rest)
</context>

<tasks>

<task type="auto">
  <name>RED: 레포 언어 비율 테스트</name>
  <files>tests/test_extractors.py</files>
  <action>
    TestExtractRepositories에 테스트 추가:
    - test_includes_language_breakdown: repositories/*.md frontmatter에 languages 필드 포함
    - FakeGitHubClient.rest에 /repos/{owner}/{repo}/languages 응답 추가
      {"Python": 50000, "JavaScript": 30000, "Shell": 5000}
    - 퍼센트 변환 확인 (Python: 58.8%, JavaScript: 35.3%, ...)
  </action>
  <verify>uv run pytest tests/test_extractors.py -k "language_breakdown" — RED</verify>
  <done>새 테스트 실패</done>
</task>

<task type="auto">
  <name>GREEN: extract_repositories에 languages API 호출 추가</name>
  <files>acta/extractors.py</files>
  <action>
    1. extract_repositories의 MD 작성 루프에서 각 레포에 대해:
       client.rest(f"/repos/{login}/{repo['name']}/languages") 호출
    2. 응답 바이트를 퍼센트로 변환 (소수점 1자리)
    3. frontmatter에 languages 필드 추가:
       languages:
         - "Python: 58.8%"
         - "JavaScript: 35.3%"
    4. extract_contributed_repos에도 동일 적용

    AVOID: languages API 실패 시 빈 리스트로 처리 — skip 하지 않기
  </action>
  <verify>uv run pytest tests/ -v — 전체 GREEN</verify>
  <done>각 레포 MD에 실제 언어 비율 포함</done>
</task>

</tasks>
