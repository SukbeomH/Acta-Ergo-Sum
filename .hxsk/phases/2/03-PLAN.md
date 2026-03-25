---
phase: 2
plan: 3
wave: 2
depends_on: [2.2]
files_modified:
  - acta/extractors.py
  - tests/test_extractors.py
  - acta/writers.py
  - acta/cli.py
autonomous: true
must_haves:
  truths:
    - "다른 사람 PR에 남긴 리뷰가 수집된다"
    - "리뷰가 reviews/YYYY-MM.md로 월별 그룹핑된다"
    - "timeline.csv에 Review 카테고리 포함"
  artifacts:
    - "acta/extractors.py에 extract_reviews() 존재"
    - "reviews/ 디렉토리에 월별 MD 생성"
---

# Plan 2.3: Code Review 활동 추출

<objective>
다른 사람의 PR에 남긴 코드 리뷰 활동을 수집한다.
현재는 본인 PR에 달린 리뷰만 포함 — 리뷰어로서의 활동이 누락됨.

Purpose: 코드 리뷰는 협업의 핵심 지표
Output: reviews/YYYY-MM.md + timeline.csv 확장
</objective>

<context>
Load for context:
- acta/extractors.py (extract_pull_requests — 리뷰 데이터 구조 참고)
- GitHub GraphQL: user.contributionsCollection.pullRequestReviewContributions
</context>

<tasks>

<task type="auto">
  <name>RED: Code Review 추출 테스트 작성</name>
  <files>tests/test_extractors.py</files>
  <action>
    TestExtractReviews 클래스:
    1. test_writes_review_files_grouped_by_month:
       - GraphQL contributionsCollection 응답 → reviews/YYYY-MM.md 생성
       - 각 리뷰: PR 제목, repo, state(APPROVED/CHANGES_REQUESTED/COMMENTED), 날짜
    2. test_stops_at_since_cutoff:
       - since 이전 리뷰 제외

    GraphQL 구조:
    user.contributionsCollection(from, to).pullRequestReviewContributions(first:100)
      → nodes: pullRequestReview { state, createdAt, pullRequest { title, url, repository } }
  </action>
  <verify>uv run pytest tests/test_extractors.py -k "Reviews" — RED</verify>
  <done>2개 테스트 ImportError로 실패</done>
</task>

<task type="auto">
  <name>GREEN: extract_reviews 구현 + CLI/timeline 연동</name>
  <files>acta/extractors.py, acta/writers.py, acta/cli.py</files>
  <action>
    1. extractors.py:
       - _REVIEW_CONTRIBUTIONS_QUERY GraphQL 쿼리
       - extract_reviews(client, base, login, since) → list[dict]
       - 월별 그룹핑 → reviews/YYYY-MM.md
    2. writers.py generate_timeline에 reviews 파라미터 추가
    3. cli.py:
       - _SUBDIRS에 "reviews" 추가
       - run()에 --skip-reviews 옵션 + extract_reviews 호출
       - generate_timeline/generate_metadata 연동

    AVOID: extract_pull_requests의 리뷰 데이터와 혼동하지 않기.
    PR 추출기의 reviews는 "내 PR에 달린 리뷰", 이 추출기는 "내가 다른 PR에 남긴 리뷰".
  </action>
  <verify>uv run pytest tests/ -v — 전체 GREEN</verify>
  <done>리뷰 활동이 월별 MD로 생성, timeline에 Review 행 포함</done>
</task>

</tasks>

<verification>
- [ ] uv run pytest tests/ -v — 전체 통과
- [ ] reviews/ 디렉토리에 월별 MD 생성
- [ ] timeline.csv에 Review 카테고리 존재
- [ ] metadata.json summary에 reviews 카운트
</verification>

<success_criteria>
- [ ] extract_reviews 함수 + 2개 테스트 통과
- [ ] "내가 남긴 리뷰"와 "내 PR에 달린 리뷰"가 분리됨
</success_criteria>
