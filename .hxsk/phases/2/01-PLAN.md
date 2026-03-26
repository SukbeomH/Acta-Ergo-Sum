---
phase: 2
plan: 1
wave: 1
depends_on: []
files_modified:
  - acta/extractors.py
  - tests/test_extractors.py
  - acta/cli.py
autonomous: true
must_haves:
  truths:
    - "COLLABORATOR/ORGANIZATION_MEMBER 레포의 커밋도 수집된다"
    - "기존 OWNER 레포 추출은 영향받지 않는다"
  artifacts:
    - "acta/extractors.py에 extract_contributed_repos() 존재"
    - "tests/test_extractors.py에 TestExtractContributedRepos 클래스 존재"
    - "commits/YYYY-MM.md에 contributed repo 커밋 포함"
---

# Plan 2.1: Contributed Repos 커밋 추출

<objective>
현재 OWNER 소유 레포만 수집하는 한계를 해결한다.
fork/collaborator/org member 레포에서 사용자가 작성한 커밋도 수집하도록 확장.

Purpose: GitHub 활동의 상당 부분이 다른 사람/조직 레포 기여인데 현재 누락됨
Output: contributed repos 목록 추출 + 해당 레포 커밋 수집
</objective>

<context>
Load for context:
- acta/extractors.py (extract_repositories, extract_commits 패턴)
- acta/client.py (GitHubClient.graphql 시그니처)
- tests/test_extractors.py (FakeGitHubClient 패턴)
</context>

<tasks>

<task type="auto">
  <name>RED: contributed repos + commits 테스트 작성</name>
  <files>tests/test_extractors.py</files>
  <action>
    1. TestExtractContributedRepos 클래스 추가:
       - test_fetches_collaborator_repos: COLLABORATOR affiliation 레포 반환 확인
       - test_excludes_owner_repos: 이미 OWNER로 수집된 레포 중복 제외 확인
    2. TestExtractCommits에 테스트 추가:
       - test_includes_contributed_repo_commits: contributed repo의 커밋도 수집되는지 확인

    GraphQL에서 ownerAffiliations: [COLLABORATOR, ORGANIZATION_MEMBER] 사용.
    extract_repositories의 기존 repos 목록을 받아 중복 제외하는 로직.
  </action>
  <verify>uv run pytest tests/test_extractors.py -k "Contributed or contributed" — RED (실패)</verify>
  <done>새 테스트가 ImportError 또는 assertion failure로 실패</done>
</task>

<task type="auto">
  <name>GREEN: extract_contributed_repos 구현 + CLI 연동</name>
  <files>acta/extractors.py, acta/cli.py</files>
  <action>
    1. extractors.py에 _CONTRIBUTED_REPO_QUERY 추가:
       - ownerAffiliations: [COLLABORATOR, ORGANIZATION_MEMBER]
       - 페이지네이션 동일 패턴
    2. extract_contributed_repos(client, base, login, since, exclude_repos) 함수:
       - exclude_repos: 이미 수집된 OWNER 레포 이름 set
       - 중복 제외 후 반환
    3. cli.py의 run()에서 extract_contributed_repos 호출:
       - repos 이후 실행, 결과를 repos에 합산
       - --skip-contributed 옵션 추가
    4. _SUBDIRS에 변경 불필요 (commits/ 디렉토리 재사용)

    AVOID: ownerAffiliations에 OWNER 포함하지 않기 — 기존 extract_repositories와 중복됨
  </action>
  <verify>uv run pytest tests/ -v — 전체 GREEN</verify>
  <done>contributed repos가 수집되고, 기존 테스트 31개 + 새 테스트 모두 통과</done>
</task>

</tasks>

<verification>
After all tasks, verify:
- [ ] uv run pytest tests/ -v — 전체 통과
- [ ] contributed repo 커밋이 commits/YYYY-MM.md에 포함
- [ ] 기존 OWNER repos 테스트 깨지지 않음
</verification>

<success_criteria>
- [ ] extract_contributed_repos 함수 존재 및 테스트 통과
- [ ] CLI --skip-contributed 옵션 동작
- [ ] 중복 레포 제외 로직 검증됨
</success_criteria>
