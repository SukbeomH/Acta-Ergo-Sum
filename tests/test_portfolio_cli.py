import json
from unittest.mock import patch

from typer.testing import CliRunner

from acta.cli import app
from acta.portfolio.workspace import Portfolio
from tests.test_portfolio import snapshot


def invoke(workspace, *args):
    return CliRunner().invoke(app, ["portfolio", "--workspace", str(workspace), *args])


def test_cancelled_editor_leaves_workspace_untouched(tmp_path):
    portfolio = Portfolio.create(tmp_path / "portfolio")
    project = portfolio.add_project("Manual", portfolio.revision)
    before = portfolio.revision
    with patch("acta.portfolio.cli.edit_text", return_value=None):
        result = invoke(portfolio.path, "claim", "edit", "--project", project)
    assert result.exit_code != 0
    assert portfolio.revision == before


def test_stale_editor_preserves_its_proposal(tmp_path):
    portfolio = Portfolio.create(tmp_path / "portfolio")
    project = portfolio.add_project("Manual", portfolio.revision)
    document = json.dumps({"scope": "individual", "role": "author", "statement": "My pending text"})
    def edit(*args, **kwargs):
        another = Portfolio.open(portfolio.path)
        another.select(project, "Another session", "public", another.revision)
        return document
    with patch("acta.portfolio.cli.edit_text", side_effect=edit):
        result = invoke(portfolio.path, "claim", "edit", "--project", project)
    assert result.exit_code == 1
    assert "preserved" in result.output
    assert next((portfolio.path / "edits").glob("*.json")).read_text() == document
    assert portfolio.reviews() == []
    assert portfolio.projects()[0]["reason"] == "Another session"


def test_wrong_approval_digest_cannot_confirm(tmp_path):
    portfolio = Portfolio.create(tmp_path / "portfolio")
    project = portfolio.add_project("Manual", portfolio.revision)
    claim = portfolio.edit_claim(project, {"scope": "individual", "role": "Author", "statement": "Wrote docs", "manual_evidence": {"excerpt": "Docs"}}, portfolio.revision)
    revision = portfolio.revision
    result = invoke(portfolio.path, "claim", "review", claim, "--approve", "wrong")
    assert result.exit_code == 1
    assert portfolio.revision == revision and portfolio.claim_review(claim)["state"] == "draft"


def test_invalid_source_does_not_create_workspace(tmp_path):
    snapshot(tmp_path)
    path = tmp_path / "source/portfolio-source.json"
    data = json.loads(path.read_text())
    data["schema_version"] = 99
    path.write_text(json.dumps(data))
    result = invoke(tmp_path / "portfolio", "init", "--source", str(path.parent))
    assert result.exit_code == 1
    assert not (tmp_path / "portfolio/workspace.sqlite3").exists()


def test_editor_process_uses_editor_setting_without_shell(tmp_path, monkeypatch):
    import shlex
    import sys
    from acta.portfolio.cli import edit_text
    editor = tmp_path / "test editor.py"
    editor.write_text("import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text('{\"edited\": true}')\n")
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", f"{shlex.quote(sys.executable)} {shlex.quote(str(editor))}")
    assert json.loads(edit_text('{"original": true}')) == {"edited": True}
