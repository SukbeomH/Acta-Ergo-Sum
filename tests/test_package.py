"""Run these checks against the installed wheel as well as the source checkout."""
import subprocess
from importlib.resources import files
from shutil import which


def test_wheel_contains_all_default_templates():
    templates = files("acta").joinpath("templates")
    assert {p.name for p in templates.iterdir() if p.name.endswith(".md")} == {
        "profile.md", "resume.md", "weekly.md", "project-summary.md"}


def test_installed_entrypoint_finds_bundled_templates(tmp_path):
    (tmp_path / "SUMMARY.md").write_text("# Portfolio evidence", encoding="utf-8")
    result = subprocess.run([which("acta"), "analyze", "-t", "profile", "-i", str(tmp_path)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "# Portfolio evidence" in (tmp_path / "analysis/profile.prompt.md").read_text()


def test_custom_template_directory_is_respected(tmp_path):
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "profile.md").write_text("CUSTOM TEMPLATE\n{{context}}", encoding="utf-8")
    result = subprocess.run([which("acta"), "analyze", "-t", "profile", "-i", str(tmp_path),
                             "--template-dir", str(custom)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "CUSTOM TEMPLATE" in (tmp_path / "analysis/profile.prompt.md").read_text()
