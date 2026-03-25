# Patterns

## Established
- **DI for testability**: GitHubClient를 함수에 주입하여 FakeClient로 테스트
- **GraphQL pagination**: cursor 기반 while loop + hasNextPage 체크
- **REST pagination**: page/per_page 파라미터 + len(data) < per_page 종료 조건
- **Output format**: YAML frontmatter + Markdown body → LLM 파싱 용이

## Anti-Patterns
- 단일 파일에 모든 로직 집중 (이미 해결)
- subprocess 직접 호출 (GitHubClient로 래핑)
