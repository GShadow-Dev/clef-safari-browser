import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest


def test_native_mcp_json_envelope_is_unwrapped():
    from mcp.types import CallToolResult, TextContent

    from clef_browser.safari import native_data

    result = CallToolResult(
        content=[
            TextContent(
                type="text", text='{"url":"https://example.org/","content":"root\\nlink uid=7"}'
            )
        ]
    )
    assert native_data(result)["content"] == "root\nlink uid=7"


def test_native_tool_errors_stop_without_replaying_actions():
    from mcp.types import CallToolResult, TextContent

    from clef_browser.safari import SafariError, native_data

    with pytest.raises(SafariError):
        native_data(CallToolResult(isError=True, content=[TextContent(type="text", text="Failed")]))


def test_native_saved_file_acknowledgment_does_not_require_json():
    from mcp.types import CallToolResult, TextContent

    from clef_browser.safari import native_data

    result = CallToolResult(
        content=[TextContent(type="text", text="Saved output to '/tmp/snapshot.txt' (502 B).")]
    )
    assert native_data(result)["text"].startswith("Saved output")


def test_input_metadata_blocks_credentials_and_ambiguous_fields():
    from clef_browser.actions import Node
    from clef_browser.safari import SafariError, validate_input

    node = Node("67", "input", "input uid=67 label='Search' placeholder='Search docs'")
    safe = {
        "tag": "input",
        "type": "search",
        "label": "Search",
        "placeholder": "Search docs",
        "autocomplete": "",
    }
    validate_input(node, {"fields": [safe]})
    for fields in [
        [{**safe, "type": "password"}],
        [{**safe, "autocomplete": "cc-number"}],
        [{**safe, "autocomplete": "CC-NUMBER"}],
        [{**safe, "autocomplete": "CURRENT-PASSWORD"}],
        [safe, safe],
        [],
    ]:
        with pytest.raises(SafariError):
            validate_input(node, {"fields": fields})


@pytest.mark.safari
@pytest.mark.skipif(os.environ.get("CLEF_TEST_SAFARI") != "1", reason="Opt-in native Safari test")
async def test_native_safari_reads_types_and_clicks_real_page(tmp_path):
    from clef_browser.actions import candidates
    from clef_browser.safari import Safari

    folder = Path(__file__).parent.parent / "examples"
    handler = partial(SimpleHTTPRequestHandler, directory=str(folder))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        async with Safari(tmp_path) as browser:
            await browser.open(f"http://127.0.0.1:{server.server_port}/fixture.html")
            before = await browser.snapshot()
            assert "Documentation directory" in before.text
            assert "never-read-this" not in before.text
            actions = candidates(before, ["Safari MCP"])
            typing = next(a for a in actions.values() if a.kind == "type")
            await browser.execute(typing, before)
            after = await browser.snapshot()
            assert "Results for: Safari MCP" in after.text
            link = next(
                a
                for a in candidates(after, []).values()
                if a.kind == "click" and "Agent guide" in a.description
            )
            await browser.execute(link, after)
            final = await browser.snapshot()
            assert final.url.endswith("/details.html")
            assert "fixture version is 1.0" in final.text
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.safari
@pytest.mark.skipif(os.environ.get("CLEF_TEST_SAFARI") != "1", reason="Opt-in native Safari test")
async def test_native_scroll_exposes_target_beyond_initial_observation(tmp_path):
    from clef_browser.actions import candidates
    from clef_browser.safari import Safari

    folder = Path(__file__).parent.parent / "examples"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(folder))
    )
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        async with Safari(tmp_path) as browser:
            await browser.open(f"http://127.0.0.1:{server.server_port}/long.html")
            await browser.call("set_viewport_size", {"width": 800, "height": 450})
            before = await browser.snapshot()
            assert "late target answer" not in before.text
            for _ in range(3):
                current = await browser.snapshot()
                await browser.execute(candidates(current, [])["scroll_down"], current)
                after = await browser.snapshot()
                if "late target answer" in after.text:
                    break
            assert "late target answer is 42" in after.text
            assert after.fingerprint != before.fingerprint
    finally:
        server.shutdown()
        server.server_close()
