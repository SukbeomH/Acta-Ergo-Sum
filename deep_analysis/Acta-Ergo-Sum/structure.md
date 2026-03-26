---
total_files: 92
extensions: 12
category: deep_structure
---

# Project Structure

**Total files**: 92

## Languages

- Python: 88.6%
- Shell: 11.4%

## File Types

| Extension | Count |
|---|---|
| `.md` | 34 |
| `.py` | 21 |
| `.gitkeep` | 19 |
| `.sh` | 7 |
| `.json` | 3 |
| `.yml` | 2 |
| `.cursorrules` | 1 |
| `.gitignore` | 1 |
| `.yaml` | 1 |
| `.python-version` | 1 |
| `.windsurfrules` | 1 |
| `.toml` | 1 |

## Directory Tree

```
.claude/
  settings.json
  skills/
    commit/
      SKILL.md
    executor/
      SKILL.md
    handoff/
      SKILL.md
    memory-protocol/
      SKILL.md
    planner/
      SKILL.md
    verifier/
      SKILL.md
.cursorrules
.github/
  copilot-instructions.md
  workflows/
    ci.yml
    publish.yml
.gitignore
.hxsk/
  ARCHITECTURE.md
  PATTERNS.md
  STACK.md
  STATE.md
  archive/
    .gitkeep
  hooks/
    _json_parse.sh
    bash-guard.py
    file-protect.py
    md-recall-memory.sh
    md-store-memory.sh
    pre-compact-save.sh
    session-start.sh
    stop-context-save.sh
    track-modifications.sh
  memories/
    _schema/
      base.schema.json
    architecture-decision/
      .gitkeep
    bootstrap/
      .gitkeep
      2026-03-25_project-bootstrap.md
    debug-blocked/
      .gitkeep
    debug-eliminated/
      .gitkeep
    decision/
      .gitkeep
    deviation/
      .gitkeep
    execution-summary/
      .gitkeep
    general/
      .gitkeep
      2026-03-25_session-handoff-hxsk.md
    health-event/
      .gitkeep
    pattern-discovery/
      .gitkeep
    pattern/
      .gitkeep
    root-cause/
      .gitkeep
    security-finding/
      .gitkeep
    session-handoff/
      .gitkeep
    session-snapshot/
      .gitkeep
    session-summary/
      .gitkeep
  phases/
    2/
      01-PLAN.md
      02-PLAN.md
      03-PLAN.md
      04-PLAN.md
      05-PLAN.md
      PHASE.md
    3/
      01-PLAN.md
      02-PLAN.md
      03-PLAN.md
      04-PLAN.md
      05-PLAN.md
      PHASE.md
  project-config.yaml
  reports/
    .gitkeep
  research/
    .gitkeep
.python-version
.superset/
  config.json
.windsurfrules
AGENTS.md
CLAUDE.md
README.md
acta/
  __init__.py
  analyzer.py
  cli.py
  client.py
  deep/
    __init__.py
    collector.py
    detector.py
    renderer.py
  extractors.py
  mcp_server.py
  writers.py
app.py
docs/
  plans/
    2026-03-25-incremental-update-design.md
    2026-03-25-llm-analysis-design.md
    2026-03-25-structure-refactor-design.md
pyproject.toml
templates/
  profile.md
  resume.md
  weekly.md
tests/
  __init__.py
  test_analyzer.py
  test_cli.py
  test_client.py
  test_deep.py
  test_extractors.py
  test_writers.py
```

## Key Files Detected

### Manifest
- `pyproject.toml`

### Ci
- `.github/workflows/ci.yml`
- `.github/workflows/publish.yml`

## Entry Points (estimated)

- `app.py`
- `acta/cli.py`
