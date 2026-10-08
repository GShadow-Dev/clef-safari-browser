import json

import pytest


@pytest.fixture(autouse=True)
def isolated_cli_configuration(tmp_path, monkeypatch):
    # Never import the developer's .env or trigger a real login in an offline test.
    monkeypatch.chdir(tmp_path)
    for name in (
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_AUTH_TOKEN",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_OAUTH_CLIENT_ID",
        "CLOUDFLARE_OAUTH_SCOPES",
    ):
        monkeypatch.delenv(name, raising=False)


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


def test_auth_status_needs_no_safari_or_credentials(tmp_path, capsys, monkeypatch):
    from clef_browser.cli import main

    monkeypatch.setenv("CLEF_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("CLOUDFLARE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert main(["auth-status"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "unlinked"


def test_login_missing_registration_explains_public_client_id(tmp_path, capsys, monkeypatch):
    from clef_browser.cli import main

    monkeypatch.setenv("CLEF_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("CLOUDFLARE_OAUTH_CLIENT_ID", raising=False)
    assert main(["login"]) == 1
    assert "CLOUDFLARE_OAUTH_CLIENT_ID" in json.loads(capsys.readouterr().out)["message"]
