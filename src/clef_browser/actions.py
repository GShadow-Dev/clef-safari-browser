"""Build a closed action set from Safari's native textTree, never model-written code."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

NODE = re.compile(r"^\s*([a-zA-Z][a-zA-Z -]*?)\s+uid=(\d+)\b(.*)$", re.MULTILINE)
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

    @property
    def sensitive(self) -> bool:
        return bool(re.search(r"\b(secure|password|file)\b", self.description, re.IGNORECASE))


@dataclass(frozen=True)
class Snapshot:
    url: str
    title: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", VALUE.sub("value=[redacted]", self.text))

    @property
    def nodes(self) -> list[Node]:
        return [Node(m[2], m[1].strip().lower(), m[0].strip()) for m in NODE.finditer(self.text)]

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

    @property
    def signature(self) -> str:
        return f"{self.kind}:{self.node}:{self.value}"


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
        snapshot.nodes, key=lambda n: -sum(word in n.description.lower() for word in terms)
    )
    for node in nodes:
        if node.sensitive:
            continue
        if node.role in {"input", "text field", "textfield", "textbox", "textarea", "searchbox"}:
            for i, text in enumerate(texts[:4]):
                key = f"type_{node.uid}_{i}"
                actions[key] = Action(
                    key,
                    "type",
                    f"Type supplied text {text[:120]!r} into {node.description[:160]} "
                    "and press Return.",
                    node.uid,
                    text,
                )
                if len(actions) >= limit:
                    return actions
        elif node.role in {"link", "button", "menuitem", "checkbox", "radio", "summary"}:
            key = f"click_{node.uid}"
            actions[key] = Action(key, "click", f"Click {node.description[:200]}", node.uid)
        if len(actions) >= limit:
            break
    return actions
