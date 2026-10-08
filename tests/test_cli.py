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
    assert {"browse", "usage", "account_usage"} <= {tool.name for tool in tools}
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


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="Native Safari uses POSIX")
def test_idle_session_exits_on_sigint_without_waiting_for_stdin_eof(tmp_path):
    import os
    import signal
    import subprocess
    import sys
    import time

    child = subprocess.Popen(
        [sys.executable, "-m", "clef_browser.cli", "session"],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "CLEF_STATE_DIR": str(tmp_path)},
    )
    try:
        time.sleep(0.7)
        child.send_signal(signal.SIGINT)
        assert child.wait(timeout=3) == 130
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=3)


def test_malformed_session_json_returns_errors_and_keeps_reading(tmp_path):
    import subprocess
    import sys

    lines = [
        {"goal": 7, "url": "https://example.org"},
        {"goal": "x", "url": "https://example.org", "texts": "abc"},
        {"goal": "x", "url": "https://example.org", "resume": "false"},
        {"goal": "x", "url": "https://example.org", "max_steps": True},
        {"command": "exit"},
    ]
    result = subprocess.run(
        [sys.executable, "-m", "clef_browser.cli", "session"],
        cwd=tmp_path,
        input="\n".join(json.dumps(line) for line in lines) + "\n",
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    outputs = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(outputs) == 4
    assert all(output["status"] == "error" for output in outputs)


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="Native Safari uses POSIX")
def test_large_tty_result_preserves_session_for_next_task(tmp_path):
    """A full native page must not crash when stdin and stdout share a terminal."""
    import os
    import pty
    import select
    import subprocess
    import sys
    import termios
    import time

    master, slave = pty.openpty()
    attributes = termios.tcgetattr(slave)
    attributes[3] &= ~termios.ECHO
    termios.tcsetattr(slave, termios.TCSANOW, attributes)
    script = """
import asyncio
from pathlib import Path
from clef_browser.cli import interactive_session
from clef_browser.config import Settings
from clef_browser.session import BrowserSession

# Replace only the external browsing operation; exercise actual CLI I/O/lifecycle.
async def page(self, task, **kwargs):
    return {'status': 'needs_input', 'goal': task.goal, 'text': 'page evidence ' * 12000}
BrowserSession.run = page
asyncio.run(interactive_session(Settings(state_dir=Path('.'))))
"""
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        stdin=slave,
        stdout=slave,
        stderr=subprocess.PIPE,
    )
    os.close(slave)
    buffered = bytearray()

    def result():
        deadline = time.monotonic() + 8
        while b"\n" not in buffered and time.monotonic() < deadline:
            readable, _, _ = select.select([master], [], [], 0.1)
            if readable:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                buffered.extend(chunk)
            if child.poll() is not None:
                break
        assert b"\n" in buffered, "CLI lost its session before completing the page result"
        line, _, remainder = buffered.partition(b"\n")
        buffered[:] = remainder
        return json.loads(line)

    try:
        os.write(master, b'{"goal":"first","url":"https://example.org"}\n')
        # Let the result exceed the terminal buffer before the consumer starts draining it.
        time.sleep(0.4)
        first = result()
        assert first["goal"] == "first"
        assert len(first["text"]) == 168000
        os.write(master, b'{"goal":"second","url":"https://example.org"}\n')
        second = result()
        assert second["goal"] == "second"
        assert second["text"] == first["text"]
        os.write(master, b'{"command":"exit"}\n')
        assert child.wait(timeout=3) == 0
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=3)
        os.close(master)


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="Native Safari uses POSIX")
@pytest.mark.parametrize("terminal", [False, True], ids=["pipe", "pty"])
def test_session_sigint_exits_with_full_output_buffer(tmp_path, terminal):
    """A slow consumer cannot trap the session in output or its cancellation report."""
    import os
    import pty
    import select
    import signal
    import subprocess
    import sys
    import time

    script = """
import sys
from clef_browser.cli import main
from clef_browser.session import BrowserSession

async def page(self, task, **kwargs):
    print('READY', file=sys.stderr, flush=True)
    return {'status': 'needs_input', 'text': 'page evidence ' * 12000}
BrowserSession.run = page
sys.exit(main(['session']))
"""
    master, slave = pty.openpty() if terminal else (None, None)
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        stdin=slave if terminal else subprocess.PIPE,
        stdout=slave if terminal else subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if slave is not None:
        os.close(slave)
    try:
        task = b'{"goal":"first","url":"https://example.org"}\n'
        if master is not None:
            os.write(master, task)
        else:
            child.stdin.write(task)
            child.stdin.flush()
        readable, _, _ = select.select([child.stderr], [], [], 3)
        assert readable and child.stderr.readline() == b"READY\n"
        # Leave output undrained, then cancel while the result exceeds its buffer.
        time.sleep(0.2)
        child.send_signal(signal.SIGINT)
        assert child.wait(timeout=3) == 130
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=3)
        if master is not None:
            os.close(master)
