---
name: project-summary
description: 레포 딥 분석 결과를 요약 — 프로젝트 소개, 기술 설명용
context:
  - overview.md
  - structure.md
  - tech_stack.md
  - evolution.md
  - community.md
max_tokens: 4096
---

You are analyzing a GitHub repository's deep analysis data to generate a project summary.

## Data

{{context}}

## Instructions

Based on the data above, generate a **project summary** in Korean:

1. **프로젝트 개요**: 이 프로젝트가 무엇인지, 어떤 문제를 해결하는지
2. **기술 스택**: 사용 언어, 프레임워크, 주요 의존성, 인프라 설정
3. **아키텍처**: 디렉토리 구조에서 파악한 설계 패턴과 모듈 구성
4. **설계 의도**: 진입점, 설정 파일, CI/CD에서 추론한 개발 철학
5. **프로젝트 성숙도**: 릴리스 이력, 커밋 빈도, 커뮤니티 건강도로 판단
6. **한줄 요약**: 포트폴리오에 넣을 수 있는 프로젝트 한줄 설명

Output as clean Markdown. 추측하지 말고 데이터에 근거해서만 작성하세요.
