import json

import pytest

from clef_browser.actions import Snapshot, candidates
from clef_browser.runner import Task, request_for
from clef_browser.safari import Safari, SafariError, validate_input

FORM = """root
    link uid=1 'Library song'
    overlay role=dialog labelledby=Create
        scrollable uid=20 scrollPosition=(0,0) contentSize=[700×990]
            uid=21 role=button expanded=true 'Lyrics'
            contentEditable uid=22 role=textbox label='Lyrics editor'
            textarea uid=23 'Style suggestions'
            input uid=24 placeholder='Song title'
            select uid=25 label=Voice
                option 'Male'
                option 'Female'
            button uid=26 'Create'
"""


def test_active_form_includes_rich_editor_role_buttons_and_nested_scroll():
    actions = candidates(Snapshot("https://example.org", "Form", FORM), ["lyrics"])
    assert "click_21" in actions
    assert actions["type_22_0"].value == "lyrics"
    assert "click_1" not in actions
    assert any(a.kind == "scroll" and a.node == "20" for a in actions.values())
    assert any(a.kind == "select" and a.value == "Male" for a in actions.values())


def test_long_exact_lyrics_stay_local_and_form_evidence_survives_library_noise():
    lyrics = "Exact lyric line\n" * 300
    task = Task("Fill lyrics and styles", "https://example.org", [lyrics, "soul"])
    snapshot = Snapshot("https://example.org", "Form", "'Library'\n" * 3000 + FORM)
    payload, actions = request_for(task, snapshot, candidates(snapshot, task.inputs), [], 6000)
    assert actions["type_22_0"].value == lyrics
    assert "Lyrics editor" in payload["state"]["observation"]["text"]
    assert len(json.dumps(payload)) < 24000
    assert lyrics not in json.dumps(payload)


def test_native_option_values_remain_selectable_while_input_values_are_redacted():
    tree = (
        "select uid=42\n\toption selected value=Male\n\toption value=Female\n"
        "input uid=43 value='private' placeholder=Search"
    )
    snapshot = Snapshot("https://example.org", "Form", tree)
    actions = candidates(snapshot, [])
    assert any(a.kind == "select" and a.value == "Female" for a in actions.values())
    assert "private" not in snapshot.text


def test_rich_and_unique_unlabeled_fields_are_validated_without_values():
    nodes = Snapshot("https://example.org", "Form", FORM).nodes
    rich = next(n for n in nodes if n.uid == "22")
    styles = next(n for n in nodes if n.uid == "23")
    field = {
        "tag": "div",
        "type": "contenteditable",
        "label": "Lyrics editor",
        "placeholder": "",
        "autocomplete": "",
    }
    validate_input(rich, {"fields": [field]})
    validate_input(
        styles,
        {
            "fields": [
                {
                    "tag": "textarea",
                    "type": "textarea",
                    "label": "",
                    "placeholder": "",
                    "autocomplete": "",
                }
            ]
        },
    )
    with pytest.raises(SafariError):
        validate_input(rich, {"fields": [{**field, "autocomplete": "one-time-code"}]})
    with pytest.raises(SafariError):
        validate_input(styles, {"fields": [{"tag": "textarea", "type": "textarea"}] * 2})


async def test_form_typing_does_not_submit_and_select_uses_observed_option(tmp_path, monkeypatch):
    browser = Safari(tmp_path)
    snapshot = Snapshot("https://example.org", "Form", FORM)
    sent = []

    async def read():
        return snapshot

    async def call(name, args):
        if name == "evaluate_javascript":
            if "dispatchEvent" in args["expression"]:
                sent.append({"notification": True})
                return {"notified": True}
            return {
                "fields": [
                    {
                        "tag": "div",
                        "type": "contenteditable",
                        "label": "Lyrics editor",
                        "placeholder": "",
                        "autocomplete": "",
                    },
                    {
                        "tag": "select",
                        "type": "select",
                        "label": "Voice",
                        "options": ["Male", "Female"],
                    },
                ]
            }
        assert name == "page_interactions"
        sent.extend(args["interactions"])
        return {}

    monkeypatch.setattr(browser, "snapshot", read)
    monkeypatch.setattr(browser, "call", call)
    actions = candidates(snapshot, ["first line\nsecond line"])
    await browser.execute(actions["type_22_0"], snapshot)
    assert sent[-1]["value"] == "first line\nsecond line"
    assert sent[-1]["pressReturn"] is False
    selection = next(a for a in actions.values() if a.kind == "select" and a.value == "Male")
    await browser.execute(selection, snapshot)
    assert sent[-2]["type"] == "selectMenuItem"
    assert sent[-2]["text"] == "Male"
    assert sent[-1] == {"notification": True}


async def test_resuming_does_not_open_a_fresh_login_session(tmp_path):
    from test_runner import Browser, Client, decision

    from clef_browser.config import Settings
    from clef_browser.runner import Runner

    browser = Browser([Snapshot("https://example.org", "Signed in", "Ready")])
    result = await Runner(
        browser, Client([decision("finish", complete=0.99)]), Settings(state_dir=tmp_path)
    ).run(Task("Check Ready", "https://example.org"), resume=True)
    assert result["status"] == "completed"
    assert not hasattr(browser, "opened")


async def test_cancel_during_input_metadata_prevents_native_typing(tmp_path, monkeypatch):
    import asyncio

    browser = Safari(tmp_path)
    cancelled = asyncio.Event()
    snapshot = Snapshot("https://example.org", "Form", "textarea uid=7")
    mutations = []

    async def read():
        return snapshot

    async def call(name, arguments):
        if name == "evaluate_javascript":
            cancelled.set()
            return {"fields": [{"tag": "textarea", "type": "textarea"}]}
        mutations.append(name)
        return {}

    monkeypatch.setattr(browser, "snapshot", read)
    monkeypatch.setattr(browser, "call", call)
    try:
        await browser.execute(
            candidates(snapshot, ["text"])["type_7_0"], snapshot, cancelled=cancelled
        )
    except SafariError:
        pass
    assert mutations == []
