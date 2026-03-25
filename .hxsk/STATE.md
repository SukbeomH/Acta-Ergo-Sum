# Project State

## Current Phase
- **Phase**: Development (PoC → Modularized)
- **Branch**: SukbeomH/poc
- **Status**: 구조 개선 완료, HXSK 설정 진행 중

## Recent Changes
- app.py (950줄 단일 파일) → acta/ 패키지 (4 모듈)로 분리
- GitHubClient 클래스 도입 (DI 기반 테스트 가능)
- pytest 29개 테스트 작성 완료
- uv 기반 pyproject.toml 마이그레이션

## Tech Stack
- Python 3.12+, uv, typer, pytest
- GitHub CLI (gh) — REST + GraphQL API
