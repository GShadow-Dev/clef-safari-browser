"""Workers AI Clef's typed-decision API (not Chat Completions)."""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from .budget import MAX_REQUEST_BYTES, RATES, Budget, encode_payload


class ClefError(RuntimeError):
    """API failure or invalid decision; messages deliberately omit payloads and tokens."""


@dataclass(frozen=True)
class Decision:
    choice: str
    probability: float
    confidence: float
    margin: float
    complete: float
    model: str

    @property
    def reliable(self) -> bool:
        return self.probability >= 0.60 and self.confidence >= 0.50 and self.margin >= 0.12


def probability(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ClefError("Invalid probability in Clef response.")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ClefError("Invalid probability in Clef response.")
    return result


def parse_decision(data: Any, criteria: dict[str, Any], model: str) -> Decision:
    try:
        if not isinstance(data, dict) or data.get("model") not in {
            model,
            f"@cf/cloudflare/{model}",
        }:
            raise ClefError("Clef returned an unexpected model.")
        answer = data["answers"]["next_action"]
        completion = data["answers"]["goal_complete"]
        if answer["type"] != "choice" or completion["type"] != "noul":
            raise ClefError("Clef returned unexpected answer types.")
        chosen = answer["choice"]
        probs = answer["probabilities"]
        if chosen not in criteria or not isinstance(probs, dict) or set(probs) != set(criteria):
            raise ClefError("Clef returned an action outside the offered candidates.")
        values = {key: probability(value) for key, value in probs.items()}
        if not math.isclose(sum(values.values()), 1, abs_tol=0.02):
            raise ClefError("Clef returned an invalid probability distribution.")
        selected = values[chosen]
        second = max(value for key, value in values.items() if key != chosen)
        if selected + 1e-8 < second:
            raise ClefError("Clef's chosen action is inconsistent with its probabilities.")
        return Decision(
            chosen,
            selected,
            probability(answer["confidence"]),
            selected - second,
            probability(completion["noul"]),
            model,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ClefError("Clef returned a malformed decision response.") from exc


class ClefClient:
    def __init__(
        self,
        account_id: str,
        token: str,
        budget: Budget,
        http: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not re.fullmatch(r"[0-9a-fA-F]{32}", account_id):
            raise ValueError("CLOUDFLARE_ACCOUNT_ID must be the 32-character account ID.")
        if not token or "\n" in token or "\r" in token:
            raise ValueError("Set a valid CLOUDFLARE_AUTH_TOKEN locally.")
        self.account_id, self.token, self.budget = account_id, token, budget
        self.http, self.sleep = http, sleep

    async def decide(self, payload: dict[str, Any], model: str = "clef-flash") -> Decision:
        if model not in RATES:
            raise ValueError("Only Clef models are supported.")
        body = {**payload, "model": model}
        encoded = encode_payload(body)
        if len(encoded) > MAX_REQUEST_BYTES or "images" in body:
            raise ValueError("Clef requests must be text-only and under 24,000 bytes.")
        criteria = body["questions"]["next_action"]["criteria"]
        if not isinstance(criteria, dict) or not 2 <= len(criteria) <= 255:
            raise ValueError("Clef requires between 2 and 255 action choices.")
        if self.http is not None:
            return await self._request(self.http, body, encoded, criteria, model)
        async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as http:
            return await self._request(http, body, encoded, criteria, model)

    async def _request(
        self,
        http: httpx.AsyncClient,
        body: dict[str, Any],
        encoded: bytes,
        criteria: dict[str, Any],
        model: str,
    ) -> Decision:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/@cf/cloudflare/{model}"
        for attempt in range(3):
            reservation = self.budget.reserve(model, body)
            retry_delay = float(2**attempt)
            try:
                result = await http.post(
                    url,
                    content=encoded,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise ClefError(
                        "Cloudflare network failure after three budgeted attempts."
                    ) from exc
                await self.sleep(retry_delay)
                continue
            try:
                envelope = result.json()
            except ValueError as exc:
                if result.status_code >= 500 and attempt < 2:
                    await self.sleep(retry_delay)
                    continue
                raise ClefError("Cloudflare returned invalid JSON.") from exc
            if not isinstance(envelope, dict):
                raise ClefError("Cloudflare returned an invalid envelope.")
            errors = envelope.get("errors") or []
            codes = {str(e.get("code")) for e in errors if isinstance(e, dict)}
            if "3036" in codes or result.status_code in {401, 403}:
                raise ClefError(
                    "Cloudflare denied access or exhausted the account allocation; check dashboard."
                )
            if result.is_success and envelope.get("success") is True:
                data = envelope.get("result")
                if not isinstance(data, dict) or not isinstance(data.get("usage"), dict):
                    raise ClefError("Clef response is missing token usage.")
                self.budget.record(reservation, data["usage"])
                return parse_decision(data, criteria, model)
            transient = result.status_code >= 500 or "3040" in codes
            if not transient or attempt == 2:
                raise ClefError(
                    f"Cloudflare inference failed (HTTP {result.status_code}); stopping."
                )
            # Honor bounded Retry-After seconds; large hints stop rather than retry too early.
            hint = result.headers.get("Retry-After", "")
            if hint:
                try:
                    retry_delay = max(retry_delay, float(hint))
                    if not math.isfinite(retry_delay) or retry_delay > 30:
                        raise ClefError(
                            "Cloudflare requested a longer retry wait; try again later."
                        )
                except ValueError:
                    raise ClefError(
                        "Cloudflare requested a dated retry; try again later."
                    ) from None
            await self.sleep(retry_delay)
        raise ClefError("Cloudflare inference did not produce a decision.")
