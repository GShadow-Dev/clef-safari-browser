"""Build a closed action set from Safari's native textTree, never model-written code."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

NODE = re.compile(r"^[ \t]*(?:([a-zA-Z][a-zA-Z -]*?)[ \t]+)?uid=(\d+)\b(.*)$", re.MULTILINE)
VALUE = re.compile(r"\bvalue=(?:'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|\S+)")


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(ord(char) < 32 for char in url)
        or len(url) > 2000
    ):
        raise ValueError("Use an HTTP(S) URL without embedded credentials.")
    return url


@dataclass(frozen=True)
class Node:
    uid: str
    role: str
    description: str
    options: tuple[str, ...] = ()

    @property
    def sensitive(self) -> bool:
        return bool(re.search(r"\b(secure|password|file)\b", self.description, re.IGNORECASE))


@dataclass(frozen=True)
class Snapshot:
    url: str
    title: str
    text: str

    def __post_init__(self) -> None:
        # Native select options may expose their label only as value=Male.
        # Options are public choices, while editable field values stay redacted.
        def redact(match: re.Match[str]) -> str:
            line_start = self.text.rfind("\n", 0, match.start()) + 1
            prefix = self.text[line_start : match.start()]
            return match[0] if re.match(r"^[ \t]*option\b", prefix) else "value=[redacted]"

        text = VALUE.sub(redact, self.text)
        object.__setattr__(self, "text", text)

    @property
    def action_text(self) -> str:
        """Prefer the active dialog over controls behind it; retain full freshness state."""
        lines = self.text.splitlines()
        dialogs = [
            i
            for i, line in enumerate(lines)
            if re.match(r"^[ \t]*overlay\b.*\brole=dialog\b", line)
        ]
        if not dialogs:
            return self.text
        start = dialogs[-1]
        depth = len(lines[start]) - len(lines[start].lstrip())
        end = start + 1
        while end < len(lines):
            line = lines[end]
            if line.strip() and len(line) - len(line.lstrip()) <= depth:
                break
            end += 1
        return "\n".join(lines[start:end])

    @property
    def nodes(self) -> list[Node]:
        nodes = []
        for m in NODE.finditer(self.text):
            role = (m[1] or "").strip().lower()
            if not role:
                aria = re.search(r"\brole=([a-z]+)\b", m[3])
                if not aria:
                    continue
                role = aria[1]
            options: tuple[str, ...] = ()
            if role == "select":
                tail = self.text[m.end() :].splitlines()
                depth = len(m[0]) - len(m[0].lstrip())
                labels = []
                for line in tail:
                    if not line.strip():
                        continue
                    if len(line) - len(line.lstrip()) <= depth:
                        break
                    if re.match(r"\s*option\b", line):
                        option = re.search(r"'([^']*)'\s*$", line)
                        if not option:
                            option = re.search(r"\bvalue=(?:'([^']*)'|\"([^\"]*)\"|(\S+))", line)
                        if option:
                            label = next((v for v in option.groups() if v), "")
                            if label:
                                labels.append(label)
                options = tuple(labels)
            nodes.append(Node(m[2], role, m[0].strip(), options))
        return nodes

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(f"{self.url}\n{self.title}\n{self.text}".encode()).hexdigest()


@dataclass(frozen=True)
class Action:
    id: str
    kind: str
    description: str
    node: str | None = None
    value: str = ""
    press_return: bool = False

    @property
    def signature(self) -> str:
        return f"{self.kind}:{self.node}:{self.value}:{self.press_return}"


def candidates(snapshot: Snapshot, texts: list[str], limit: int = 48) -> dict[str, Action]:
    if not 5 <= limit <= 128:
        raise ValueError("Candidate limit must be between 5 and 128.")
    actions = {
        "finish": Action(
            "finish", "finish", "Finish ONLY if the goal is fully achieved in observed evidence."
        ),
        "stop": Action(
            "stop", "stop", "Stop: login, CAPTCHA, missing input, unsafe task, or no useful action."
        ),
        "scroll_down": Action(
            "scroll_down", "scroll", "Scroll down to reveal more page content.", value="640"
        ),
        "scroll_up": Action(
            "scroll_up", "scroll", "Scroll up to earlier page content.", value="-640"
        ),
        "wait": Action("wait", "wait", "Wait briefly for this page to update."),
    }
    terms = {word for text in texts for word in re.findall(r"\w{3,}", text.lower())}
    nodes = sorted(
        Snapshot(snapshot.url, snapshot.title, snapshot.action_text).nodes,
        key=lambda n: -sum(word in n.description.lower() for word in terms),
    )
    for node in nodes:
        if node.sensitive:
            continue
        if node.role in {
            "input",
            "text field",
            "textfield",
            "textbox",
            "textarea",
            "searchbox",
            "contenteditable",
        }:
            for i, text in enumerate(texts[:4]):
                key = f"type_{node.uid}_{i}"
                actions[key] = Action(
                    key,
                    "type",
                    f"Type supplied text {text[:120]!r} into {node.description[:160]} "
                    f"({len(text)} characters). Replace the field without submitting.",
                    node.uid,
                    text,
                )
                if len(actions) >= limit:
                    return actions
                if (
                    node.role in {"input", "searchbox", "text field", "textfield"}
                    and "search" in node.description.lower()
                ):
                    submit_key = f"search_{node.uid}_{i}"
                    actions[submit_key] = Action(
                        submit_key,
                        "type",
                        f"Search for supplied text {text[:120]!r} in {node.description[:160]} "
                        "and press Return.",
                        node.uid,
                        text,
                        True,
                    )
                    if len(actions) >= limit:
                        return actions
        elif node.role == "select":
            for i, option in enumerate(node.options):
                key = f"select_{node.uid}_{i}"
                actions[key] = Action(
                    key,
                    "select",
                    f"Select observed option {option!r} in {node.description[:160]}",
                    node.uid,
                    option,
                )
                if len(actions) >= limit:
                    return actions
        elif node.role == "scrollable":
            for direction, delta in (("down", "640"), ("up", "-640")):
                key = f"scroll_{node.uid}_{direction}"
                actions[key] = Action(
                    key,
                    "scroll",
                    f"Scroll {direction} inside {node.description[:140]}",
                    node.uid,
                    delta,
                )
                if len(actions) >= limit:
                    return actions
        elif node.role in {
            "link",
            "button",
            "menuitem",
            "checkbox",
            "radio",
            "summary",
            "combobox",
            "option",
            "switch",
        }:
            key = f"click_{node.uid}"
            actions[key] = Action(key, "click", f"Click {node.description[:200]}", node.uid)
        if len(actions) >= limit:
            break
    return actions
