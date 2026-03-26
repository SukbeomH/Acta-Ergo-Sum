"""핵심 파일 자동 감지 — 트리에서 중요한 파일을 찾아낸다."""

from __future__ import annotations

import fnmatch
from typing import Any


# 카테고리별 감지 대상 파일 패턴
KEY_FILE_PATTERNS: dict[str, list[str]] = {
    "manifest": [
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "Gemfile",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "composer.json",
        "mix.exs",
        "deno.json",
        "pubspec.yaml",
    ],
    "infra": [
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "Makefile",
        "justfile",
        "Taskfile.yml",
        "Procfile",
        "Vagrantfile",
        "terraform/*.tf",
        "k8s/*.yaml",
        "helm/Chart.yaml",
    ],
    "ci": [
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        ".gitlab-ci.yml",
        "Jenkinsfile",
        ".circleci/config.yml",
        ".travis.yml",
        "azure-pipelines.yml",
    ],
    "docs": [
        "CONTRIBUTING.md",
        "ARCHITECTURE.md",
        "DESIGN.md",
        "CHANGELOG.md",
        "CHANGES.md",
        "SECURITY.md",
        "docs/README.md",
        "docs/index.md",
        "docs/architecture.md",
        "ADR/*.md",
        "adr/*.md",
    ],
    "config": [
        ".env.example",
        ".env.sample",
        "tsconfig.json",
        "vite.config.*",
        "next.config.*",
        "webpack.config.*",
        "tailwind.config.*",
        "babel.config.*",
        "eslint.config.*",
        ".eslintrc.*",
        "prettier.config.*",
        "ruff.toml",
        "setup.cfg",
    ],
}

# 진입점 감지 패턴 (우선순위 순)
ENTRY_POINT_PATTERNS: list[str] = [
    "main.*",
    "index.*",
    "app.*",
    "server.*",
    "cli.*",
    "cmd/main.*",
    "src/main.*",
    "src/index.*",
    "src/app.*",
    "src/lib.*",
    "lib/index.*",
]

# 진입점으로 간주하지 않는 확장자
_SKIP_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".lock", ".css", ".svg", ".png", ".jpg"}


def detect_key_files(
    tree_paths: list[str], category: str | None = None,
) -> dict[str, list[str]]:
    """트리 경로 목록에서 카테고리별 핵심 파일을 찾는다.

    category가 주어지면 해당 카테고리만 반환한다.
    """
    categories = {category: KEY_FILE_PATTERNS[category]} if category else KEY_FILE_PATTERNS
    result: dict[str, list[str]] = {}

    for cat, patterns in categories.items():
        matched: list[str] = []
        for pattern in patterns:
            for path in tree_paths:
                if fnmatch.fnmatch(path, pattern):
                    if path not in matched:
                        matched.append(path)
        if matched:
            result[cat] = sorted(matched)

    return result


def detect_entry_points(
    tree_paths: list[str], manifest_hint: str | None = None,
) -> list[str]:
    """프로젝트 진입점 파일을 추정한다.

    manifest_hint: 매니페스트에서 추출한 진입점 경로 (e.g. "src/index.ts").
    """
    entries: list[str] = []

    # 매니페스트 힌트가 있으면 최우선
    if manifest_hint and manifest_hint in tree_paths:
        entries.append(manifest_hint)

    # 패턴 매칭
    for pattern in ENTRY_POINT_PATTERNS:
        for path in tree_paths:
            # 최상위 또는 src/ 아래만 (깊은 경로 제외)
            depth = path.count("/")
            if depth > 2:
                continue
            ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
            if ext in _SKIP_EXTENSIONS:
                continue
            if fnmatch.fnmatch(path.split("/")[-1], pattern.split("/")[-1]):
                if path not in entries:
                    entries.append(path)

    return entries[:5]  # 최대 5개


def build_tree_summary(tree_paths: list[str], max_depth: int = 3) -> str:
    """파일 트리를 depth 제한하여 텍스트 트리로 렌더링한다."""
    dirs: dict[str, int] = {}
    file_count = 0

    for path in tree_paths:
        parts = path.split("/")
        file_count += 1
        # 각 depth별 디렉토리 카운트
        for i in range(min(len(parts) - 1, max_depth)):
            dir_path = "/".join(parts[: i + 1])
            dirs[dir_path] = dirs.get(dir_path, 0) + 1

    # 트리 렌더링
    lines: list[str] = []
    rendered: set[str] = set()

    for path in sorted(tree_paths):
        parts = path.split("/")
        if len(parts) - 1 > max_depth:
            # 깊은 파일: max_depth까지 디렉토리를 표시하고 축약
            for i in range(min(len(parts) - 1, max_depth)):
                dir_path = "/".join(parts[: i + 1])
                if dir_path not in rendered:
                    indent = "  " * i
                    lines.append(f"{indent}{parts[i]}/")
                    rendered.add(dir_path)
            # 축약된 하위 표시
            dir_path = "/".join(parts[:max_depth])
            collapse_key = f"_collapse_{dir_path}"
            if collapse_key not in rendered:
                indent = "  " * max_depth
                count = dirs.get(dir_path, 0)
                lines.append(f"{indent}… ({count} files)")
                rendered.add(collapse_key)
            continue

        # 디렉토리 경로 표시
        for i in range(len(parts) - 1):
            dir_path = "/".join(parts[: i + 1])
            if dir_path not in rendered:
                indent = "  " * i
                lines.append(f"{indent}{parts[i]}/")
                rendered.add(dir_path)

        # 파일 표시
        indent = "  " * (len(parts) - 1)
        lines.append(f"{indent}{parts[-1]}")

    return "\n".join(lines)


def count_by_extension(tree_paths: list[str]) -> dict[str, int]:
    """확장자별 파일 수를 집계한다."""
    counts: dict[str, int] = {}
    for path in tree_paths:
        if "." in path.split("/")[-1]:
            ext = "." + path.rsplit(".", 1)[-1]
            counts[ext] = counts.get(ext, 0) + 1
        else:
            counts["(no ext)"] = counts.get("(no ext)", 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))
