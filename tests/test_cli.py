import json


def test_missing_credentials_is_actionable_json_and_no_browser_launch(
    tmp_path, capsys, monkeypatch
):
    from clef_browser.cli import main

    monkeypatch.setenv("CLEF_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    code = main(["run", "--goal", "Open docs", "--url", "https://example.org/"])
    output = json.loads(capsys.readouterr().out)
    assert code == 1
    assert output["status"] == "error"
    assert "CLOUDFLARE_ACCOUNT_ID" in output["message"]


def test_budget_command_works_without_cloudflare_or_safari(tmp_path, capsys, monkeypatch):
    from clef_browser.cli import main

    monkeypatch.setenv("CLEF_STATE_DIR", str(tmp_path))
    assert main(["budget"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["reserved_neurons"] == 0
    assert output["limit_neurons"] == 8000


def test_task_validation_precedes_any_external_action(tmp_path, capsys, monkeypatch):
    from clef_browser.cli import main

    monkeypatch.setenv("CLEF_STATE_DIR", str(tmp_path))
    assert main(["run", "--goal", "x", "--url", "javascript:alert(1)"]) == 1
    assert "HTTP(S)" in json.loads(capsys.readouterr().out)["message"]


async def test_mcp_server_exposes_shared_browse_and_usage_tools(tmp_path):
    from clef_browser.config import Settings
    from clef_browser.server import create_server

    server = create_server(Settings(state_dir=tmp_path))
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {"browse", "usage"}
    assert "goal" in next(tool for tool in tools if tool.name == "browse").inputSchema["properties"]
