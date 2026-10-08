from clef_browser.config import Settings
from clef_browser.runner import Task


async def test_persistent_worker_retains_browser_across_human_login_and_closes_once(
    tmp_path, monkeypatch
):
    from test_runner import Client, decision

    from clef_browser import session
    from clef_browser.actions import Snapshot

    events = []

    class Browser:
        async def __aenter__(self):
            events.append("connect")
            return self

        async def __aexit__(self, *args):
            events.append("close")

        async def open(self, url):
            events.append("open")

        async def snapshot(self):
            return Snapshot("https://example.org", "Session", "Ready")

        async def execute(self, action, expected, *, cancelled=None):
            raise AssertionError("No mutation expected")

    async def client_for(settings, budget):
        return Client([decision("stop"), decision("finish", complete=0.99)])

    monkeypatch.setattr(session, "Safari", lambda *args: Browser())
    monkeypatch.setattr(session, "client_for", client_for)
    async with session.BrowserSession(Settings(state_dir=tmp_path)) as worker:
        first = await worker.run(Task("Check Ready", "https://example.org"))
        assert first["status"] == "needs_input"
        second = await worker.run(Task("Check Ready", "https://example.org"), resume=True)
        assert second["status"] == "completed"
        assert events == ["connect", "open"]
    assert events == ["connect", "open", "close"]


async def test_resume_without_a_session_does_not_launch_browser(tmp_path):
    from clef_browser.session import BrowserSession

    async with BrowserSession(Settings(state_dir=tmp_path)) as worker:
        result = await worker.run(Task("Resume", "https://example.org"), resume=True)
        assert result["status"] == "error"
        assert "session" in result["message"].lower()


async def test_cancelled_caller_stops_before_the_next_browser_mutation(tmp_path, monkeypatch):
    import asyncio

    import pytest
    from test_runner import Browser, decision, pages

    from clef_browser import session

    started, release = asyncio.Event(), asyncio.Event()
    browser = Browser(pages())

    class Native:
        async def __aenter__(self):
            return browser

        async def __aexit__(self, *args):
            pass

    class Client:
        async def decide(self, *args):
            started.set()
            await release.wait()
            return decision("click_7")

    async def client_for(*args):
        return Client()

    monkeypatch.setattr(session, "Safari", lambda *args: Native())
    monkeypatch.setattr(session, "client_for", client_for)
    async with session.BrowserSession(Settings(state_dir=tmp_path)) as worker:
        caller = asyncio.create_task(worker.run(Task("Find version", "https://example.org/")))
        await started.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        try:
            result = await asyncio.wait_for(
                worker.run(Task("Next task", "https://example.org/")), 0.1
            )
            assert result["status"] == "busy"
        finally:
            release.set()
    assert browser.executed == []
