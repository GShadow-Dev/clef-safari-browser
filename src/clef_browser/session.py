"""Keep the native SDK in one owning task across browsing and human handoffs."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from .auth import client_for
from .budget import Budget, BudgetExceeded
from .clef import ClefError
from .config import Settings
from .oauth import OAuthError
from .runner import Runner, Task
from .safari import Safari, SafariError


class BrowserSession:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.worker: asyncio.Task[None] | None = None
        self.busy = asyncio.Lock()
        self.connected = False
        self.active = False

    async def __aenter__(self) -> BrowserSession:
        self.worker = asyncio.create_task(self._work())
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.queue.put(None)
        if self.worker:
            await self.worker

    async def run(
        self, task: Task, *, resume: bool = False, max_steps: int | None = None
    ) -> dict[str, Any]:
        if not isinstance(resume, bool):
            raise ValueError("Resume must be a boolean.")
        if max_steps is not None and type(max_steps) is not int:
            raise ValueError("Maximum steps must be an integer.")
        configured = replace(
            self.settings,
            max_steps=min(
                max_steps if max_steps is not None else self.settings.max_steps,
                self.settings.max_steps,
            ),
        )
        if self.worker is None or self.worker.done():
            return {"status": "error", "message": "The browser session is closed."}
        if resume and not self.connected:
            return {
                "status": "error",
                "message": "No active browser session to resume; start a task first.",
            }
        if self.busy.locked() or self.active:
            return {"status": "busy", "message": "Another task is using this browser session."}
        async with self.busy:
            future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
            cancelled = asyncio.Event()
            self.active = True
            await self.queue.put((task, resume, configured, future, cancelled))
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                cancelled.set()
                raise

    async def _work(self) -> None:
        # SDK AnyIO cancel scopes must enter and exit in this same task, even
        # though MCP tool requests are executed in different request tasks.
        while (job := await self.queue.get()) is not None:
            future = job[3]
            try:
                budget = Budget(
                    self.settings.state_dir / "usage.sqlite3", self.settings.daily_neurons
                )
                client = await client_for(self.settings, budget)
                async with Safari(self.settings.state_dir, self.settings.driver) as browser:
                    self.connected = True
                    while job is not None:
                        task, resume, configured, future, cancelled = job
                        result = await Runner(browser, client, configured, budget).run(
                            task, resume=resume, cancelled=cancelled
                        )
                        if not future.done():
                            future.set_result(result)
                        self.active = False
                        job = await self.queue.get()
                    return
            except (ValueError, SafariError, ClefError, BudgetExceeded, OAuthError) as exc:
                if not future.done():
                    future.set_result({"status": "error", "message": str(exc)})
            except Exception:
                if not future.done():
                    future.set_result(
                        {
                            "status": "error",
                            "message": "The browser session stopped unexpectedly; "
                            "no action was retried.",
                        }
                    )
            finally:
                self.connected = False
                self.active = False
