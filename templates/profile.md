---
name: profile
description: 기술 프로필 생성 — 포트폴리오, 소개 페이지용
context:
  - SUMMARY.md
  - metadata.json
max_tokens: 4096
---

You are analyzing a developer's GitHub activity data to generate a technical profile.

## Data

{{context}}

## Instructions

Based on the data above, generate a **technical profile** in Korean:

1. **한줄 소개**: 이 개발자를 한 문장으로 설명
2. **주요 기술 스택**: 언어, 프레임워크, 도구 (데이터 기반)
3. **핵심 프로젝트**: 가장 활발한 레포 3-5개와 각각의 역할/기여
4. **활동 패턴**: 커밋 빈도, PR 스타일, 협업 방식
5. **관심 분야**: starred repos와 topics에서 추론한 기술적 관심사
6. **강점 요약**: 데이터에서 드러나는 개발자로서의 강점

Output as clean Markdown. 추측하지 말고 데이터에 근거해서만 작성하세요.
