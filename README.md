# Acta Ergo Sum

> *I act, therefore I am.*

A CLI tool that collects your GitHub activity and structures it into an
LLM-friendly **Markdown knowledge base** — complete with YAML Frontmatter,
a `metadata.json` index, and a `timeline.csv` for time-series analysis.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | `python --version` |
| [GitHub CLI (`gh`)](https://cli.github.com/) | Must be installed and authenticated (`gh auth login`) |

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Collect the last 365 days of activity (default)
python app.py run

# Custom period and output directory
python app.py run --days 90 --output ./my_data

# Skip slow steps for a quick run
python app.py run --days 30 --skip-readmes

# Show authenticated user
python app.py whoami
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--days` | `365` | How many past days of activity to collect |
| `--output` | `./acta_data` | Output base directory |
| `--skip-readmes` | `false` | Skip README archival (faster) |
| `--skip-commits` | `false` | Skip commit extraction |
| `--skip-prs` | `false` | Skip pull request extraction |
| `--skip-stars` | `false` | Skip star extraction |

---

## Output Structure

```text
acta_data/
├── repositories/          # One .md per repo (language, topics, fork status)
├── commits/               # YYYY-MM.md — commits grouped by month
├── pull_requests/         # One .md per PR (reviews, state, description)
├── readmes/               # Archived README.md files
├── stars/                 # YYYY-MM.md — starred repos grouped by month
├── projects/              # GitHub Projects (v2) info
├── organizations/         # Orgs you belong to
├── metadata.json          # LLM-friendly index of everything
└── timeline.csv           # Chronological log: date, category, repo, action
```

Each Markdown file starts with **YAML Frontmatter** for easy parsing:

```markdown
---
name: my-repo
created_at: 2023-01-15T10:00:00Z
language: Python
topics:
  - cli
  - data-engineering
is_fork: false
---

## my-repo
…
```

---

## Architecture

```
app.py
 └─ CLI (Typer)
     └─ run()
         ├─ extract_repositories()   → repositories/*.md
         ├─ extract_commits()        → commits/YYYY-MM.md
         ├─ extract_pull_requests()  → pull_requests/*.md
         ├─ extract_readmes()        → readmes/*_readme.md
         ├─ extract_stars()          → stars/YYYY-MM.md
         ├─ extract_projects()       → projects/*.md
         ├─ extract_organizations()  → organizations/*.md
         ├─ generate_metadata()      → metadata.json
         └─ generate_timeline()      → timeline.csv
```

All `gh` CLI calls go through `_run_gh()` / `_run_gh_graphql()` helpers
that handle pagination and rate-limit back-off automatically.
