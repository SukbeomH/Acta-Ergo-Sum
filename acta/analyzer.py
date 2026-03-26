"""LLM 분석 파이프라인 — 프롬프트 조합 + API 호출."""

from __future__ import annotations

import glob
from pathlib import Path
from typing import Any


def load_template(path: Path) -> tuple[dict[str, Any], str]:
    """YAML frontmatter + 프롬프트 본문을 파싱한다."""
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter_str = parts[1].strip()
    body = parts[2].strip()

    meta = _parse_simple_yaml(frontmatter_str)
    return meta, body


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """간단한 YAML frontmatter를 파싱한다 (외부 의존성 없음)."""
    result: dict[str, Any] = {}
    current_key = ""
    current_list: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("- ") and current_key:
            current_list.append(stripped[2:].strip())
            continue

        if current_key and current_list:
            result[current_key] = current_list
            current_list = []
            current_key = ""

        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if not value:
                current_key = key
                current_list = []
            else:
                # 타입 추론
                if value.isdigit():
                    result[key] = int(value)
                elif value.startswith("[") and value.endswith("]"):
                    items = [i.strip() for i in value[1:-1].split(",") if i.strip()]
                    result[key] = items
                else:
                    result[key] = value

    if current_key and current_list:
        result[current_key] = current_list

    return result


def build_prompt(
    template_body: str, context_files: list[str], data_dir: Path
) -> str:
    """{{context}} 자리에 파일 내용을 삽입한다."""
    context_parts: list[str] = []

    for pattern in context_files:
        if "*" in pattern or "?" in pattern:
            matched = sorted(glob.glob(str(data_dir / pattern)))
            for match in matched:
                p = Path(match)
                if p.is_file():
                    context_parts.append(
                        f"### {p.name}\n\n{p.read_text(encoding='utf-8')}"
                    )
        else:
            file_path = data_dir / pattern
            if file_path.is_file():
                context_parts.append(
                    f"### {pattern}\n\n{file_path.read_text(encoding='utf-8')}"
                )

    context_str = "\n\n".join(context_parts)
    return template_body.replace("{{context}}", context_str)


def list_templates(templates_dir: Path) -> list[str]:
    """templates 디렉토리의 .md 파일 이름 목록을 반환한다."""
    if not templates_dir.is_dir():
        return []
    return sorted(p.stem for p in templates_dir.glob("*.md"))


def call_api(prompt: str, max_tokens: int = 4096, model: str = "claude-sonnet-4-20250514") -> str:
    """Anthropic Claude API를 호출한다."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic SDK가 설치되지 않았습니다. "
            "`uv add anthropic`으로 설치하세요."
        )

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
