---
phase: 3
plan: 5
wave: 1
depends_on: []
files_modified:
  - acta/extractors.py
  - tests/test_extractors.py
autonomous: true
must_haves:
  truths:
    - "stars/*.md에 각 star 레포의 description, language, topics가 포함된다"
    - "Star 레포 정보로 기술적 관심사를 상세히 추론할 수 있다"
  artifacts:
    - "stars/YYYY-MM.md body에 description, topics 포함"
---

# Plan 3.5: Star 레포 상세 정보

<objective>
현재 stars/*.md는 이름과 날짜만 포함한다.
GraphQL starredRepositories에서 이미 description, topics, language를
수집하고 있으므로, MD 출력에 이를 더 풍부하게 반영한다.

추가로 star 레포의 README 첫 줄(tagline)을 포함하면
"왜 이 레포에 관심을 가졌는지" LLM이 추론하기 좋다.

Purpose: Star 데이터를 기술적 관심사 프로파일링에 활용 가능하게
Output: stars/*.md body 확장
</objective>

<context>
- acta/extractors.py (extract_stars, _STARS_QUERY)
</context>

<tasks>

<task type="auto">
  <name>RED: Star 상세 정보 테스트</name>
  <files>tests/test_extractors.py</files>
  <action>
    TestExtractStars에 테스트 추가:
    - test_includes_star_details: stars/*.md에 다음 포함 확인:
      - description
      - topics
      - language
      - stargazerCount
    - GraphQL mock에 해당 필드 포함 (이미 _make_star_edge에 있음)
  </action>
  <verify>uv run pytest tests/test_extractors.py -k "star_details" — RED</verify>
  <done>새 테스트 실패</done>
</task>

<task type="auto">
  <name>GREEN: stars MD body 확장</name>
  <files>acta/extractors.py</files>
  <action>
    extract_stars의 MD 작성 부분에서 각 star entry의 body를 확장:
    ```
    ### [{name}]({url})
    - **Starred**: {date}
    - **Language**: {language}
    - **Stars**: {stargazerCount}
    - **Description**: {description}
    - **Topics**: {topics}
    ```

    이미 수집하고 있는 데이터를 출력만 확장하면 되므로 API 변경 없음.
  </action>
  <verify>uv run pytest tests/ -v — 전체 GREEN</verify>
  <done>Star MD에 상세 정보 포함</done>
</task>

</tasks>
