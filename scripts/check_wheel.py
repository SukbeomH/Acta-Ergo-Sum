"""Install a wheel in isolation and exercise its entry point and MCP protocol.

Usage: uv run python scripts/check_wheel.py dist/acta_ergo_sum-0.1.0-py3-none-any.whl
"""
import shutil
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    wheel = Path(sys.argv[1]).resolve(strict=True)
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="acta-wheel-") as directory:
        temp = Path(directory)
        for name in ["test_package.py", "test_mcp.py"]:
            shutil.copy2(source / "tests" / name, temp / name)
        env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
        for extra, tests in [("", [temp / "test_package.py"]), ("[mcp]", [temp])]:
            subprocess.run([
                "uv", "run", "--isolated", "--no-project", "--python", sys.executable,
                "--with", f"{wheel}{extra}", "--with", "pytest>=8", "python", "-m", "pytest", "-q",
                *map(str, tests),
            ], cwd=temp, env=env, check=True, timeout=180)


if __name__ == "__main__":
    main()
