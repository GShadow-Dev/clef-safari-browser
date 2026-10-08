from collections import deque

import pytest


class Browser:
    def __init__(self, snapshots, fail=None):
        self.snapshots = deque(snapshots)
        self.current = snapshots[0]
        self.executed = []
        self.fail = fail

    async def open(self, url):
        self.opened = url

    async def snapshot(self):
        if self.snapshots:
            self.current = self.snapshots.popleft()
        return self.current

    async def execute(self, action, expected, *, cancelled=None):
        if self.fail:
            error, self.fail = self.fail, None
            raise error
        self.executed.append(action.id)


class Client:
    def __init__(self, decisions):
        self.decisions = deque(decisions)
        self.models = []

    async def decide(self, payload, model="clef-flash"):
        self.models.append(model)
        assert payload["questions"]["next_action"]["type"] == "choice"
        return self.decisions.popleft()


def decision(choice, complete=0.1, reliable=True, model="clef-flash"):
    from clef_browser.clef import Decision

    return Decision(
        choice,
        0.95 if reliable else 0.4,
        0.9 if reliable else 0.2,
        0.8 if reliable else 0.01,
        complete,
        model,
    )


def pages():
    from clef_browser.actions import Snapshot

    return [
        Snapshot("https://example.org/", "Directory", "link uid=7 'Agent guide'"),
        Snapshot("https://example.org/docs", "Guide", "The fixture version is 1.0"),
    ]


async def test_success_returns_browsed_evidence_and_actual_action_history(tmp_path):
    from clef_browser.config import Settings
    from clef_browser.runner import Runner, Task

    browser = Browser(pages())
    result = await Runner(
        browser,
        Client([decision("click_7"), decision("finish", complete=0.98)]),
        Settings(state_dir=tmp_path),
    ).run(Task("Find the fixture version", "https://example.org/"))
    assert result["status"] == "completed"
    assert result["pages"][-1]["url"] == "https://example.org/docs"
    assert "1.0" in result["pages"][-1]["text"]
    assert result["history"][0]["action"] == "click_7"


async def test_false_finish_does_not_claim_completion(tmp_path):
    from clef_browser.config import Settings
    from clef_browser.runner import Runner, Task

    result = await Runner(
        Browser(pages()), Client([decision("finish", complete=0.3)]), Settings(state_dir=tmp_path)
    ).run(Task("Find version", "https://example.org/"))
    assert result["status"] == "needs_input"


async def test_low_confidence_can_escalate_once_with_same_candidates(tmp_path):
    from clef_browser.config import Settings
    from clef_browser.runner import Runner, Task

    client = Client(
        [
            decision("click_7", reliable=False),
            decision("click_7", model="clef"),
            decision("finish", complete=0.98),
        ]
    )
    result = await Runner(Browser(pages()), client, Settings(state_dir=tmp_path)).run(
        Task("Find version", "https://example.org/")
    )
    assert result["status"] == "completed"
    assert client.models == ["clef-flash", "clef", "clef-flash"]


async def test_low_confidence_never_executes_when_escalation_disabled(tmp_path):
    from clef_browser.config import Settings
    from clef_browser.runner import Runner, Task

    browser = Browser(pages())
    result = await Runner(
        browser,
        Client([decision("click_7", reliable=False)]),
        Settings(state_dir=tmp_path, escalate=False),
    ).run(Task("Find version", "https://example.org/"))
    assert result["status"] == "needs_input"
    assert browser.executed == []


async def test_stale_decision_is_discarded_without_executing_old_action(tmp_path):
    from clef_browser.actions import Snapshot
    from clef_browser.config import Settings
    from clef_browser.runner import Runner, Task
    from clef_browser.safari import StaleSnapshot

    browser = Browser(
        [pages()[0], Snapshot("https://example.org/", "Updated", "link uid=8 'New docs'")],
        fail=StaleSnapshot("changed"),
    )
    result = await Runner(
        browser, Client([decision("click_7"), decision("stop")]), Settings(state_dir=tmp_path)
    ).run(Task("Find version", "https://example.org/"))
    assert browser.executed == []
    assert result["status"] == "needs_input"
    assert result["history"][0]["status"] == "stale"


async def test_browser_action_failure_is_not_retried(tmp_path):
    from clef_browser.config import Settings
    from clef_browser.runner import Runner, Task
    from clef_browser.safari import SafariError

    client = Client([decision("click_7")])
    result = await Runner(
        Browser(pages(), fail=SafariError("failed")), client, Settings(state_dir=tmp_path)
    ).run(Task("Find version", "https://example.org/"))
    assert result["status"] == "error"
    assert len(client.models) == 1


async def test_max_steps_and_unchanged_repeated_action_stop(tmp_path):
    from clef_browser.config import Settings
    from clef_browser.runner import Runner, Task

    browser = Browser([pages()[0]])
    result = await Runner(
        browser,
        Client([decision("click_7"), decision("click_7")]),
        Settings(state_dir=tmp_path, max_steps=2),
    ).run(Task("Find version", "https://example.org/"))
    assert result["status"] == "stalled"
    assert browser.executed == ["click_7"]


@pytest.mark.parametrize(
    "goal,url,texts",
    [
        ("", "https://example.org/", []),
        ("x", "javascript:alert(1)", []),
        ("x", "https://example.org/", ["x" * 10001]),
    ],
)
def test_task_validation_refuses_invalid_inputs(goal, url, texts):
    from clef_browser.runner import Task

    with pytest.raises(ValueError):
        Task(goal, url, texts)
