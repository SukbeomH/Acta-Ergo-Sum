---
name: weekly
description: 주간/월간 활동 리포트 — 팀 공유, 회고용
context:
  - SUMMARY.md
  - timeline.csv
max_tokens: 4096
---

You are generating a weekly/monthly activity report from a developer's GitHub data.

## Data

{{context}}

## Instructions

Based on the data above, generate an **activity report** in Korean:

1. **기간 요약**: 이 기간 동안의 주요 활동 한줄 요약
2. **핵심 성과**: 완료된 PR, 해결한 이슈, 주요 커밋 (구체적으로)
3. **프로젝트별 진행 상황**: 레포별로 어떤 작업을 했는지
4. **협업 활동**: 코드 리뷰, 이슈 코멘트 등
5. **다음 주 예상 작업**: 진행 중인 PR/이슈 기반으로 추론

Output as clean Markdown. 간결하게 작성하세요.
