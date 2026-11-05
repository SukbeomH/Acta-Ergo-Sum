# Verification — 2026-11-05

- Baseline: ee9cfe0, existing suite 83 passing.
- Failing-before checks: six initial regressions reproduced monthly history loss, owner collisions, PR/issue cutoff omissions, successful exit after API failure, and missing default templates outside the checkout. MCP startup failed with both SDK 2.3.0 and 1.30.0 before dependency/API fixes. Additional migration and long-review-range regressions failed before their fixes.
- Final Python 3.13 suite: 111 passed.
- Final Python 3.12 suite: 111 passed (`uv run --isolated --python 3.12 --extra mcp pytest tests/ -q`).
- `uv build`: source distribution and wheel built successfully.
- `scripts/check_wheel.py`: 4 passed on each of Python 3.12 and 3.13, using an isolated installed wheel outside the source tree. Checks bundled/custom templates, installed CLI entry point, MCP initialize/list/call, and protocol-only stdout.
- Live public GitHub checks: `acta deep SukbeomH/Acta-Ergo-Sum` completed; MCP initialize and `get_repo_structure` returned the repository tree including app.py.
- `git diff --check`: passed.
- No real account activity export or paid LLM call was needed. API failure paths use deterministic synthetic responses.
