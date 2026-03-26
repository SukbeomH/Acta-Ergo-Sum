---
languages:
  - Python
  - Shell
dependency_managers:
category: deep_tech_stack
---

# Tech Stack

## Languages

- Python: 88.6%
- Shell: 11.4%

## Configuration Files

### `pyproject.toml`

```toml
[project]
name = "acta-ergo-sum"
version = "0.1.0"
description = "GitHub activity data extractor — I act, therefore I am."
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
authors = [
    { name = "Sukbeom H" },
]
keywords = ["github", "cli", "portfolio", "resume", "knowledge-base", "llm", "mcp"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "License :: OSI Approved :: MIT License",
    "Topic :: Software Development :: Documentation",
    "Topic :: Software Development :: Libraries",
    "Environment :: Console",
    "Intended Audience :: Developers",
]
dependencies = [
    "typer>=0.9.0",
]

[project.optional-dependencies]
mcp = ["mcp[cli]>=1.0.0"]

[project.urls]
Homepage = "https://github.com/SukbeomH/Acta-Ergo-Sum"
Repository = "https://github.com/SukbeomH/Acta-Ergo-Sum"
Issues = "https://github.com/SukbeomH/Acta-Ergo-Sum/issues"

[project.scripts]
acta = "acta.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["acta"]

[dependency-groups]
dev = [
    "pytest>=8.0",
]

```

### `.github/workflows/ci.yml`

```yml
name: CI

on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          version: "latest"

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - run: uv sync --dev
      - run: uv run pytest tests/ -v

```

### `.github/workflows/publish.yml`

```yml
name: Publish to PyPI

on:
  push:
    tags:
      - "v*"

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          version: "latest"

      - run: uv sync --dev
      - run: uv run pytest tests/ -v

  publish:
    needs: test
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          version: "latest"

      - run: uv build
      - run: uv publish --trusted-publishing always

```

