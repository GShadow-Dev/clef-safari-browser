"""Official Safari MCP transport. Own snapshots, local lock, bounded calls, no action retry."""

from __future__ import annotations

import asyncio
import fcntl
import json
import re
import subprocess
import sys
from contextlib import AsyncExitStack
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TextIO

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from .actions import Action, Node, Snapshot, validate_url

# Safari 27.0 advertises $uid(N) in evaluate_javascript, but this build does not
# expand that macro (verified against the live server). Inspect only fixed field
# metadata locally; execution still targets native UIDs through page_interactions.
INPUT_METADATA = """return {fields: Array.from(document.querySelectorAll('input,textarea'))
  .filter(e => e.getClientRects().length && !e.disabled)
  .map(e => ({tag: e.tagName.toLowerCase(), type: e.type || '',
    autocomplete: e.autocomplete || '', placeholder: e.getAttribute('placeholder') || '',
    label: e.getAttribute('aria-label') ||
      (e.getAttribute('aria-labelledby') || '').split(/\\s+/).map(id =>
        document.getElementById(id)?.textContent || '').join(' ').trim() ||
      Array.from(e.labels || []).map(l => l.textContent.trim()).join(' ')
  }))};"""


class SafariError(RuntimeError):
    """Safari could not safely perform a requested operation."""


class StaleSnapshot(SafariError):
    """The page changed after Clef made its decision."""


def validate_input(node: Node, metadata: dict[str, Any]) -> None:
    identifiers = dict(re.findall(r"\b(label|placeholder)='([^']*)'", node.description))
    if not identifiers:
        raise SafariError(
            "Unlabeled input cannot be identified reliably; use a labeled search field."
        )
    fields = metadata.get("fields")
    if not isinstance(fields, list):
        raise SafariError("Safari input metadata was unreadable.")
    matches = [
        item
        for item in fields
        if isinstance(item, dict)
        and all(item.get(key) == value for key, value in identifiers.items())
    ]
    if len(matches) != 1:
        raise SafariError("The input is missing or ambiguous; fill it manually in Safari.")
    field = matches[0]
    if field.get("tag") not in {"input", "textarea"} or field.get("type") not in {
        "text",
        "search",
        "email",
        "url",
        "tel",
        "number",
        "textarea",
    }:
        raise SafariError("This field cannot be filled by a browsing action.")
    if re.search(r"password|cc-|one-time-code", str(field.get("autocomplete", "")), re.IGNORECASE):
        raise SafariError("Enter credentials or payment information manually in Safari.")


def native_data(result: CallToolResult) -> dict[str, Any]:
    if result.isError:
        raise SafariError(
            "Safari tool failed; check remote automation, page state, and other sessions."
        )
    if result.structuredContent:
        return result.structuredContent
    for block in result.content:
        if block.type == "text":
            try:
                data = json.loads(block.text)
            except ValueError:
                continue
            if isinstance(data, dict):
                return data
    texts = [block.text for block in result.content if block.type == "text"]
    if texts:
        return {"text": "\n".join(texts)}
    raise SafariError("Safari returned an unsupported response format.")


class Safari:
    def __init__(self, state_dir: Path, driver: str = "/usr/bin/safaridriver") -> None:
        self.state_dir, self.driver = state_dir, driver
        self.stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.lock_file: TextIO | None = None
        self.temp_dir: str = ""

    async def __aenter__(self) -> Safari:
        if sys.platform != "darwin":
            raise SafariError("Native Safari requires macOS with Safari 27 or newer.")
        try:
            version = await asyncio.to_thread(
                subprocess.run,
                [self.driver, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SafariError("Safari driver is unavailable; install Safari 27 or newer.") from exc
        major = re.search(r"Safari (\d+)", version.stdout)
        if version.returncode or not major or int(major[1]) < 27:
            raise SafariError("This project requires Safari 27+ with its built-in MCP server.")
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        await self.stack.__aenter__()
        try:
            self.lock_file = self.stack.enter_context((self.state_dir / "safari.lock").open("a"))
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SafariError(
                    "Another Clef Safari session is running. Wait for it to finish."
                ) from exc
            self.temp_dir = self.stack.enter_context(TemporaryDirectory(prefix="clef-safari-"))
            errlog = self.stack.enter_context((Path(self.temp_dir) / "driver.log").open("w"))
            streams = await self.stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(command=self.driver, args=["--mcp"]),
                    errlog=errlog,
                )
            )
            read_stream, write_stream = streams
            session = await self.stack.enter_async_context(
                ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(seconds=45),
                )
            )
            self.session = session
            await session.initialize()
            catalog = await session.list_tools()
            required = {
                "create_tab",
                "get_page_content",
                "page_interactions",
                "page_info",
                "evaluate_javascript",
            }
            if not required <= {tool.name for tool in catalog.tools}:
                raise SafariError(
                    "Safari's MCP tool catalog has changed; review the native adapter."
                )
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *args: Any) -> None:
        # Do not inject caller exceptions into the SDK's AnyIO task groups, which
        # would wrap an ordinary SafariError in nested ExceptionGroups.
        await self.stack.aclose()

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.session is None:
            raise SafariError("Safari is not connected.")
        try:
            result = await self.session.call_tool(
                name, arguments, read_timeout_seconds=timedelta(seconds=45)
            )
        except Exception as exc:
            raise SafariError(
                "Safari call timed out or disconnected. Enable Safari Settings → Developer → "
                "Allow remote automation and external agents; use one automation session."
            ) from exc
        return native_data(result)

    async def open(self, url: str) -> None:
        await self.call("create_tab", {"url": validate_url(url)})

    async def snapshot(self) -> Snapshot:
        # Always use a path we created, never a server/page-provided arbitrary file path.
        target = Path(self.temp_dir) / "snapshot.txt"
        target.unlink(missing_ok=True)
        data = await self.call(
            "get_page_content",
            {
                "format": "textTree",
                "nodeIds": "interactive",
                "region": "viewport",
                "includeURLs": True,
                "includeAccessibilityAttributes": True,
                "maxWordsPerParagraph": 80,
                "savePath": str(target),
            },
        )
        info = await self.call("page_info", {})
        if target.is_file():
            # Cap local extraction too; bounded state and candidate set are sent later.
            with target.open() as source:
                text = source.read(262144)
            try:
                saved = json.loads(text)
                text = saved.get("content", text) if isinstance(saved, dict) else text
            except ValueError:
                pass
        else:
            text = data.get("content", "")
        if not isinstance(text, str) or not text:
            raise SafariError("Safari returned no page text. The page may still be loading.")
        return Snapshot(str(info.get("url", "")), str(info.get("title", "")), text)

    async def execute(self, action: Action, expected: Snapshot) -> None:
        fresh = await self.snapshot()
        if fresh.fingerprint != expected.fingerprint:
            raise StaleSnapshot("The page changed while Clef decided; observing again.")
        if action.kind == "wait":
            await asyncio.sleep(1)
            return
        interaction: dict[str, Any] = {"purpose": action.description, "type": action.kind}
        if action.kind == "scroll":
            interaction["scrollDelta"] = {"x": 0, "y": int(action.value)}
        elif action.kind in {"click", "type"}:
            node = next((n for n in fresh.nodes if n.uid == action.node), None)
            if node is None or node.sensitive or action.node is None or not action.node.isdigit():
                raise StaleSnapshot(
                    "The selected element is missing or sensitive; observing again."
                )
            if action.kind == "type":
                # Metadata only: never read values, cookies, storage, or credential contents.
                metadata = await self.call("evaluate_javascript", {"expression": INPUT_METADATA})
                validate_input(node, metadata)
                interaction.update(value=action.value, replaceAll=True, pressReturn=True)
            interaction.update(node=action.node, scrollToVisible=True)
        else:
            raise SafariError("Unsupported browser action.")
        await self.call("page_interactions", {"interactions": [interaction], "fullText": True})
