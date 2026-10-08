"""Let any MCP-compatible agent use the same Cloudflare-decided Safari loop."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from .budget import Budget, BudgetExceeded
from .clef import ClefError
from .config import Settings
from .credits import credits_report
from .oauth import OAuthError
from .runner import Task
from .safari import SafariError
from .session import BrowserSession


def create_server(settings: Settings) -> FastMCP:
    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[BrowserSession]:
        async with BrowserSession(settings) as session:
            yield session

    server = FastMCP(
        "clef-safari-browser",
        instructions="Browse in native Safari using Cloudflare Clef's bounded decisions. "
        "Supply a concrete goal, HTTP(S) start URL and exact search/input texts. "
        "Review returned status and source-page evidence. Credentials stay local. "
        "Use resume=true after a login handoff to retain the same task tab.",
        lifespan=lifespan,
    )

    @server.tool()
    async def browse(
        goal: str,
        url: str,
        ctx: Context[Any, BrowserSession, Any],
        texts: list[str] | None = None,
        max_steps: int = 24,
        resume: bool = False,
    ) -> dict[str, Any]:
        """Browse with Clef choosing every action; return evidence, status and budget usage."""
        try:
            task = Task(goal, url, texts or [])
            session = ctx.request_context.lifespan_context
            return await session.run(task, resume=resume, max_steps=max_steps)
        except (ValueError, SafariError, ClefError, BudgetExceeded, OAuthError) as exc:
            return {"status": "error", "message": str(exc)}

    @server.tool()
    def usage() -> dict[str, Any]:
        """Read local UTC-day reserved neurons. Other account usage is not reflected here."""
        return Budget(settings.state_dir / "usage.sqlite3", settings.daily_neurons).usage()

    @server.tool()
    async def account_usage() -> dict[str, Any]:
        """Check Cloudflare's account-wide neuron estimate and local budget. No inference."""
        return await credits_report(settings)

    return server
