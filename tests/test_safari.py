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


async def test_snapshot_selects_only_the_tab_created_by_this_adapter(tmp_path, monkeypatch):
    from clef_browser.safari import Safari

    browser = Safari(tmp_path)
    browser.temp_dir = str(tmp_path)
    calls = []

    async def call(name, arguments):
        calls.append((name, arguments))
        if name == "create_tab":
            return {"handle": "page-65F2D53E-C04A-435A-A2B2-EAEBA4D2B670"}
        if name == "get_page_content":
            return {"content": "root\nbutton uid=7 'Ready'"}
        if name == "page_info":
            return {"url": "https://example.org", "title": "Ready"}
        assert name == "switch_tab"
        assert arguments == {"handle": "page-65F2D53E-C04A-435A-A2B2-EAEBA4D2B670"}
        return {}

    monkeypatch.setattr(browser, "call", call)
    await browser.open("https://example.org")
    await browser.snapshot()
    assert [name for name, args in calls] == [
        "create_tab",
        "switch_tab",
        "get_page_content",
        "page_info",
    ]


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
            typing = next(a for a in actions.values() if a.kind == "type" and a.press_return)
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
async def test_native_rich_lyrics_styles_and_dropdown_do_not_submit_form(tmp_path):
    from clef_browser.actions import candidates
    from clef_browser.safari import Safari

    folder = Path(__file__).parent.parent / "examples"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(folder))
    )
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        async with Safari(tmp_path) as browser:
            await browser.open(f"http://127.0.0.1:{server.server_port}/form.html")
            before = await browser.snapshot()
            lyrics = "Exact lyric line\n" * 300
            actions = candidates(before, [lyrics])
            rich = next(
                a for a in actions.values() if a.kind == "type" and "Lyrics editor" in a.description
            )
            await browser.execute(rich, before)
            after = await browser.snapshot()
            assert "Lyrics chars: 4800" in after.text and "Old draft" not in after.text
            assert "Not submitted" in after.text
            styles = next(
                a
                for a in candidates(after, ["soul"]).values()
                if a.kind == "type" and "textarea" in a.description
            )
            await browser.execute(styles, after)
            after = await browser.snapshot()
            assert "Styles entered: soul" in after.text
            selection = next(
                (
                    a
                    for a in candidates(after, []).values()
                    if a.kind == "select" and a.value == "Female"
                ),
                None,
            )
            assert selection is not None, after.text
            await browser.execute(selection, after)
            after = await browser.snapshot()
            assert "Voice selected: Female" in after.text
            assert "Not submitted" in after.text
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
