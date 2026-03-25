---
name: resume
description: 이력서/CV 초안 — 프로젝트 경험 중심
context:
  - SUMMARY.md
  - metadata.json
  - repositories/*.md
max_tokens: 8192
---

You are drafting a resume/CV based on a developer's GitHub activity data.

## Data

{{context}}

## Instructions

Based on the data above, generate a **resume draft** in Korean:

1. **기술 요약** (3-4줄): 주요 기술 스택과 경험 영역
2. **프로젝트 경험** (각 프로젝트별):
   - 프로젝트명 + 한줄 설명
   - 사용 기술
   - 주요 기여 (커밋 수, PR 수 등 정량적 데이터 포함)
   - 기간
3. **기술 스킬**:
   - 언어: 숙련도 순
   - 프레임워크/도구
4. **오픈소스 기여**: 외부 프로젝트 기여 이력 (있는 경우)

Output as clean Markdown. 이력서 형식에 맞게 간결하고 전문적으로 작성하세요.
데이터에 없는 내용은 절대 추가하지 마세요.
