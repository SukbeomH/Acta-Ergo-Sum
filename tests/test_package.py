"""Run these checks against the installed wheel as well as the source checkout."""
import subprocess
from importlib.resources import files
from pathlib import Path
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


def test_installed_portfolio_manual_round_trip(tmp_path):
    import json
    workspace = tmp_path / "portfolio"
    def run(*args, success=True):
        result = subprocess.run([which("acta"), "portfolio", "--workspace", str(workspace), *args],
                                cwd=tmp_path, capture_output=True, text=True, timeout=30)
        if success:
            assert result.returncode == 0, result.stderr + result.stdout
        else:
            assert result.returncode != 0
        return result.stdout.strip()
    run("init")
    project = run("add-project", "--name", "Manual project")
    run("select", project, "--reason", "Relevant work", "--disclosure", "public")
    document = {"scope": "individual", "role": "Implemented the deploy command", "problem": "Manual release steps", "action": "Built deploy CLI",
                "result": "Repeatable deployment", "statement": "Built a deployment CLI with documented steps.", "evidence_ids": [],
                "manual_evidence": {"excerpt": "I wrote the deploy command and its operator guide.", "disclosure": "public"},
                "result_kind": "qualitative", "metrics": [], "disclosure": "public"}
    source = tmp_path / "claim.json"
    source.write_text(json.dumps(document))
    claim = run("claim", "edit", "--project", project, "--file", str(source)).splitlines()[-1]
    view = json.loads(run("claim", "review", claim, "--show"))
    run("claim", "review", claim, "--approve", view["digest"], "--revision", str(view["revision"]))
    draft = run("draft", "create", "--project", project)
    run("export", draft, "--output", str(tmp_path / "exports"), success=False)
    view = json.loads(run("draft", "review", draft, "--show"))
    run("draft", "review", draft, "--approve", view["digest"], "--revision", str(view["revision"]))
    bundle = Path(run("export", draft, "--output", str(tmp_path / "exports")))
    assert "Built a deployment CLI" in (bundle / "document.md").read_text()
    assert json.loads((bundle / "evidence.json").read_text())["evidence"][0]["provenance"] == "self_reported"
    run("refresh")
    run("backup", "--output", str(tmp_path / "backup.sqlite3"))
    assert (tmp_path / "backup.sqlite3").stat().st_size > 0
