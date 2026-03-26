---
phase: 2
plan: 5
wave: 3
depends_on: [2.1, 2.2, 2.3, 2.4]
files_modified:
  - tests/test_cli.py
autonomous: true
must_haves:
  truths:
    - "CLI run 커맨드가 end-to-end로 동작한다"
    - "모든 --skip-* 옵션이 해당 추출기를 건너뛴다"
    - "whoami 커맨드가 사용자 이름을 출력한다"
  artifacts:
    - "tests/test_cli.py 파일 존재"
    - "TestCliRun, TestCliWhoami 클래스 존재"
---

# Plan 2.5: CLI 통합 테스트

<objective>
Typer CliRunner로 CLI 커맨드의 end-to-end 흐름을 검증한다.

Purpose: 개별 모듈 테스트는 있지만 오케스트레이션 레벨 검증이 없음
Output: tests/test_cli.py
</objective>

<context>
Load for context:
- acta/cli.py (run, whoami 커맨드)
- acta/client.py (GitHubClient — mock 대상)
</context>

<tasks>

<task type="auto">
  <name>RED: CLI 통합 테스트 작성</name>
  <files>tests/test_cli.py</files>
  <action>
    1. GitHubClient를 monkeypatch로 FakeGitHubClient로 교체
    2. TestCliRun:
       - test_run_creates_output_directory: run 후 acta_data/ 구조 생성 확인
       - test_run_with_skip_options: --skip-commits --skip-prs 시 해당 디렉토리 비어있음
       - test_run_generates_metadata_and_timeline: metadata.json, timeline.csv 생성 확인
    3. TestCliWhoami:
       - test_whoami_prints_username: "Authenticated as: testuser" 출력 확인

    typer.testing.CliRunner 사용.
    subprocess.run을 mock하여 gh CLI 호출 차단.
  </action>
  <verify>uv run pytest tests/test_cli.py -v — RED</verify>
  <done>4개 테스트 실패</done>
</task>

<task type="auto">
  <name>GREEN: CLI 통합 테스트 통과시키기</name>
  <files>tests/test_cli.py, acta/cli.py</files>
  <action>
    1. FakeGitHubClient를 conftest.py 또는 test_cli.py에 정의
       - 모든 API 호출에 최소한의 유효 응답 반환
    2. monkeypatch로 GitHubClient 생성자를 FakeGitHubClient로 교체
    3. cli.py에 수정이 필요하면 최소 변경만 (테스트 가능성 개선)

    AVOID: 실제 gh CLI를 호출하지 않기 — 모든 외부 호출 mock
    AVOID: conftest.py에 복잡한 fixture 남발하지 않기 — test_cli.py 내에서 자체 완결
  </action>
  <verify>uv run pytest tests/ -v — 전체 GREEN</verify>
  <done>CLI 통합 테스트 4개 + 기존 테스트 모두 통과</done>
</task>

</tasks>

<verification>
- [ ] uv run pytest tests/ -v — 전체 통과
- [ ] CliRunner로 실행한 run 커맨드가 exit code 0
- [ ] --skip-* 옵션 검증됨
</verification>

<success_criteria>
- [ ] tests/test_cli.py 존재 + 4개 테스트 통과
- [ ] 실제 gh CLI 호출 없이 테스트 완료
</success_criteria>
