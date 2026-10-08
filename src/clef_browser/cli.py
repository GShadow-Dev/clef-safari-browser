"""JSON CLI with explicit live probes and no implicit Cloudflare billing changes."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from typing import Any

from . import __version__
from .budget import RATES, Budget, BudgetExceeded
from .clef import ClefClient, ClefError
from .config import Settings
from .runner import Task, browse_task
from .safari import Safari, SafariError


async def doctor(settings: Settings, url: str | None, cloudflare: bool) -> dict[str, Any]:
    report: dict[str, Any] = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "driver": settings.driver,
        "model": settings.model,
        "cloudflare_credentials_configured": bool(settings.account_id and settings.token),
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
        result = await ClefClient(settings.account_id, settings.token, budget).decide(
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
            "Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_AUTH_TOKEN locally, "
            "then run doctor --cloudflare."
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
    commands.add_parser("serve", help="Expose browse and usage tools over stdio MCP.")
    return cli


def emit(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        settings = Settings.from_env(args.env_file)
        if args.command == "serve":
            from .server import create_server

            create_server(settings).run(transport="stdio")
            return 0
        if args.command == "budget":
            emit(Budget(settings.state_dir / "usage.sqlite3", settings.daily_neurons).usage())
            return 0
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
    except (ValueError, SafariError, ClefError, BudgetExceeded) as exc:
        emit({"status": "error", "message": str(exc)})
        return 1
    except KeyboardInterrupt:
        emit({"status": "cancelled", "message": "Stopped by the user."})
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
