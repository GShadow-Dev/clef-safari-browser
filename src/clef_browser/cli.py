"""JSON CLI with explicit live probes and no implicit Cloudflare billing changes."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from typing import Any

from . import __version__
from .auth import auth_status, client_for, login, logout
from .budget import RATES, Budget, BudgetExceeded
from .clef import ClefError
from .config import Settings
from .credits import credits_report
from .oauth import OAuthConfig, OAuthError
from .runner import Task, browse_task
from .safari import Safari, SafariError
from .session import BrowserSession


async def interactive_session(settings: Settings) -> int:
    """Read one task JSON per line, retaining Safari until stdin closes."""
    reader = asyncio.StreamReader(limit=1048576)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer
    )
    try:
        async with BrowserSession(settings) as session:
            while line := await reader.readline():
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        raise ValueError("Each line must be a task JSON object.")
                    if data.get("command") == "exit":
                        break
                    result = await session.run(
                        Task(data["goal"], data["url"], data.get("texts", [])),
                        resume=data.get("resume", False),
                        max_steps=data.get("max_steps"),
                    )
                except (ValueError, KeyError, TypeError) as exc:
                    result = {"status": "error", "message": str(exc)}
                print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
    finally:
        transport.close()
    return 0


async def doctor(settings: Settings, url: str | None, cloudflare: bool) -> dict[str, Any]:
    connection = auth_status(settings)
    report: dict[str, Any] = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "driver": settings.driver,
        "model": settings.model,
        "cloudflare_credentials_configured": connection["status"] in {"linked", "configured"},
        "authentication": connection,
        "cloudflare_live_verified": False,
        "native_navigation_verified": False,
        "neurons_per_million_input_tokens": RATES[settings.model],
    }
    async with Safari(settings.state_dir, settings.driver) as browser:
        report["safari_mcp_ready"] = True
        if url:
            await browser.open(url)
            snapshot = await browser.snapshot()
            report.update(
                native_navigation_verified=True, page_url=snapshot.url, page_title=snapshot.title
            )
    if cloudflare:
        budget = Budget(settings.state_dir / "usage.sqlite3", settings.daily_neurons)
        client = await client_for(settings, budget)
        result = await client.decide(
            {
                "state": "This is a connectivity probe. No browser action should be executed.",
                "questions": {
                    "next_action": {
                        "type": "choice",
                        "instructions": "Choose stop for this probe.",
                        "criteria": {
                            "stop": "Stop the connectivity probe.",
                            "finish": "Finish a browsing task.",
                        },
                    },
                    "goal_complete": {
                        "type": "noul",
                        "instructions": "Is this only a connectivity probe?",
                    },
                },
            },
            settings.model,
        )
        report.update(
            cloudflare_live_verified=True, probe_choice=result.choice, budget=budget.usage()
        )
    report["status"] = "ready"
    if not report["cloudflare_credentials_configured"]:
        report["next_step"] = (
            "Run clef-browser login to link Cloudflare, then doctor --cloudflare. "
            "See docs/oauth.md for OAuth client registration."
        )
    return report


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Use Cloudflare Clef to browse in native Safari.")
    cli.add_argument("--version", action="version", version=__version__)
    cli.add_argument(
        "--env-file", help="Explicit .env path; otherwise use .env in current directory."
    )
    commands = cli.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="Browse and return status, source evidence and action history as JSON."
    )
    run.add_argument("--goal", required=True)
    run.add_argument("--url", required=True)
    run.add_argument(
        "--text",
        "--query",
        action="append",
        default=[],
        help="Exact input/search text; repeat up to four times.",
    )
    run.add_argument("--max-steps", type=int)
    run.add_argument("--model", choices=list(RATES))
    run.add_argument("--no-escalation", action="store_true")
    probe = commands.add_parser(
        "doctor", help="Check native MCP; live probes require explicit flags."
    )
    probe.add_argument("--url", help="Open and read this URL to verify native navigation.")
    probe.add_argument(
        "--cloudflare", action="store_true", help="Make one small budgeted live Clef inference."
    )
    commands.add_parser("budget", help="Show local allocation usage without network access.")
    commands.add_parser("credits", help="Check account-wide Cloudflare neurons and local budget.")
    commands.add_parser("serve", help="Expose browsing and usage tools over stdio MCP.")
    commands.add_parser(
        "session", help="Persistent Safari: one task JSON per stdin line; resume after login."
    )
    auth = commands.add_parser(
        "login", help="Link a Cloudflare account using Safari and OAuth PKCE."
    )
    auth.add_argument("--client-id", help="Public OAuth client ID; never a client secret.")
    auth.add_argument("--account-id", help="Account selected during Cloudflare consent.")
    auth.add_argument(
        "--scope", action="append", help="Registered Workers AI scope ID; repeat for each."
    )
    auth.add_argument("--port", type=int, help="Must match the registered loopback callback URL.")
    commands.add_parser("auth-status", help="Show connection metadata without tokens or inference.")
    commands.add_parser(
        "logout", help="Revoke and remove this app's OAuth connection; retain budget."
    )
    return cli


def emit(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        settings = Settings.from_env(args.env_file)
        if args.command == "auth-status":
            emit(auth_status(settings))
            return 0
        if args.command == "login":
            config = OAuthConfig(
                args.client_id or settings.oauth_client_id,
                args.account_id or settings.account_id,
                tuple(args.scope or settings.oauth_scopes),
                args.port if args.port is not None else settings.oauth_port,
            )
            print(
                "Opening Cloudflare authorization in Safari. Review the account and permissions.",
                file=sys.stderr,
            )
            emit(asyncio.run(login(settings, config)))
            return 0
        if args.command == "logout":
            emit(asyncio.run(logout(settings)))
            return 0
        if args.command == "serve":
            from .server import create_server

            create_server(settings).run(transport="stdio")
            return 0
        if args.command == "session":
            return asyncio.run(interactive_session(settings))
        if args.command == "budget":
            emit(Budget(settings.state_dir / "usage.sqlite3", settings.daily_neurons).usage())
            return 0
        if args.command == "credits":
            report = asyncio.run(credits_report(settings))
            emit(report)
            return 0 if report["status"] == "ready" else 1
        if args.command == "doctor":
            emit(asyncio.run(doctor(settings, args.url, args.cloudflare)))
            return 0
        task = Task(args.goal, args.url, args.text)
        settings = replace(
            settings,
            max_steps=args.max_steps if args.max_steps is not None else settings.max_steps,
            model=args.model or settings.model,
            escalate=settings.escalate and not args.no_escalation,
        )
        result = asyncio.run(browse_task(task, settings))
        emit(result)
        return 0 if result["status"] == "completed" else 1
    except (ValueError, SafariError, ClefError, BudgetExceeded, OAuthError) as exc:
        emit({"status": "error", "message": str(exc)})
        return 1
    except KeyboardInterrupt:
        emit({"status": "cancelled", "message": "Stopped by the user."})
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
