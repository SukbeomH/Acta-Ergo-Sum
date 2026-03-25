---
phase: 3
plan: 4
wave: 2
depends_on: [3.2]
files_modified:
  - acta/extractors.py
  - tests/test_extractors.py
autonomous: true
must_haves:
  truths:
    - "각 레포 MD에 About/description이 포함된다"
    - "README 내용이 요약되어 레포 MD body에 포함된다"
    - "레포 프로필에서 '이 프로젝트가 무엇인지' 한눈에 파악 가능"
  artifacts:
    - "repositories/*.md body에 About + README 요약 포함"
---

# Plan 3.4: 레포 상세 정보 보강

<objective>
현재 repositories/*.md는 메타데이터(stars, language, topics)만 포함하고
프로젝트가 "무엇을 하는지"에 대한 설명이 부족하다.

description(About)은 이미 수집 중이지만 body에 더 풍부한 컨텍스트를 추가한다:
- About(description) 강조 표시
- README의 첫 부분 요약 (이미 readmes/에 있는 데이터 활용)
- 최근 활동 요약 (마지막 push 날짜, 커밋 수)

Purpose: LLM이 레포를 프로파일링할 때 "이 프로젝트가 뭔지" 맥락 제공
Output: repositories/*.md body 확장
</objective>

<context>
- acta/extractors.py (extract_repositories — body 생성 부분)
- 기존 readmes/ 디렉토리 (extract_readmes로 수집된 데이터)
</context>

<tasks>

<task type="auto">
  <name>RED: 레포 상세 정보 테스트</name>
  <files>tests/test_extractors.py</files>
  <action>
    TestExtractRepositories에 테스트 추가:
    - test_includes_rich_body: repositories/*.md body에 다음 포함 확인:
      - About 섹션 (description)
      - pushed_at 표시
      - stars/forks 수
  </action>
  <verify>uv run pytest tests/test_extractors.py -k "rich_body" — RED</verify>
  <done>새 테스트 실패</done>
</task>

<task type="auto">
  <name>GREEN: 레포 MD body 확장</name>
  <files>acta/extractors.py</files>
  <action>
    1. extract_repositories의 body 생성 부분을 확장:
       ```
       ## {repo_name}

       > {description}

       - **Language**: {language}
       - **Stars**: {stars} | **Forks**: {forks}
       - **Last push**: {pushed_at}
       - **Topics**: {topics}
       ```
    2. extract_contributed_repos에도 동일 적용

    AVOID: README 내용을 여기서 인라인하지 않기 — readmes/ 디렉토리에 이미 있으므로 참조만
  </action>
  <verify>uv run pytest tests/ -v — 전체 GREEN</verify>
  <done>레포 MD body에 풍부한 메타데이터 포함</done>
</task>

</tasks>
