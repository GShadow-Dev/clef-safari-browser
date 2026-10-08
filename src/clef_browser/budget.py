"""Conservative, cross-process UTC-day reservations. Failed calls are never refunded."""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Published October 7, 2026. Review against docs/sources.md on upgrades.
RATES = {"clef-flash": 8182, "clef": 21818}
MAX_REQUEST_BYTES = 24000


class BudgetExceeded(RuntimeError):
    """No further inference should be attempted."""


def encode_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class Reservation:
    id: str
    day: str
    model: str
    neurons: int
    input_bound: int


class Budget:
    def __init__(
        self,
        path: Path,
        limit: float = 8000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not math.isfinite(limit) or not 0 < limit <= 10000:
            raise ValueError("Daily budget must be greater than 0 and at most 10,000 neurons.")
        self.path, self.limit = path, limit
        self.clock = clock or (lambda: datetime.now(UTC))
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY, day TEXT NOT NULL, model TEXT NOT NULL,
                neurons INTEGER NOT NULL, input_bound INTEGER NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0, recorded INTEGER NOT NULL DEFAULT 0
            )""")
            db.execute(
                "CREATE TABLE IF NOT EXISTS budget_flags "
                "(day TEXT PRIMARY KEY, reason TEXT NOT NULL)"
            )
        self.path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def _day(self) -> str:
        return self.clock().astimezone(UTC).date().isoformat()

    def reserve(self, model: str, payload: dict[str, Any]) -> Reservation:
        if model not in RATES:
            raise ValueError("Only clef and clef-flash are allowed by the free-tier budget.")
        size = len(encode_payload(payload))
        if size > MAX_REQUEST_BYTES or "images" in payload:
            raise ValueError("Requests must be text-only and at most 24,000 UTF-8 bytes.")
        bound = math.ceil((size + 1024) * 1.25)
        amount = math.ceil(bound * RATES[model] / 1_000_000)
        reservation = Reservation(uuid.uuid4().hex, self._day(), model, amount, bound)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            blocked = db.execute(
                "SELECT reason FROM budget_flags WHERE day=?", (reservation.day,)
            ).fetchone()
            if blocked:
                raise BudgetExceeded(str(blocked[0]))
            used = db.execute(
                "SELECT COALESCE(SUM(neurons), 0) FROM reservations WHERE day=?",
                (reservation.day,),
            ).fetchone()[0]
            if used + amount > self.limit:
                raise BudgetExceeded(
                    f"Daily local budget exhausted ({used}/{self.limit:g} neurons reserved). "
                    "Allocation resets at 00:00 UTC; check Cloudflare account usage too."
                )
            db.execute(
                "INSERT INTO reservations(id, day, model, neurons, input_bound) "
                "VALUES (?, ?, ?, ?, ?)",
                (reservation.id, reservation.day, model, amount, bound),
            )
        return reservation

    def record(self, reservation: Reservation, usage: dict[str, Any]) -> None:
        tokens = usage.get("input_tokens")
        if type(tokens) is not int or tokens < 0:
            raise ValueError("Clef returned invalid input-token usage.")
        actual = math.ceil(tokens * RATES[reservation.model] / 1_000_000)
        anomaly = actual > reservation.neurons or tokens > reservation.input_bound
        reason = "Cloudflare usage exceeded the estimate; inference is blocked until the UTC reset."
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE reservations SET neurons=MAX(neurons, ?), input_tokens=?, recorded=1 "
                "WHERE id=?",
                (actual, tokens, reservation.id),
            )
            if anomaly:
                db.execute(
                    "INSERT OR REPLACE INTO budget_flags(day, reason) VALUES (?, ?)",
                    (reservation.day, reason),
                )
        if anomaly:
            raise BudgetExceeded(reason)

    def usage(self) -> dict[str, Any]:
        day = self._day()
        with self._connect() as db:
            used, requests, tokens = db.execute(
                "SELECT COALESCE(SUM(neurons), 0), COUNT(*), COALESCE(SUM(input_tokens), 0) "
                "FROM reservations WHERE day=?",
                (day,),
            ).fetchone()
            blocked = db.execute("SELECT reason FROM budget_flags WHERE day=?", (day,)).fetchone()
        return {
            "utc_day": day,
            "reserved_neurons": used,
            "limit_neurons": self.limit,
            "remaining_neurons": max(0, self.limit - used),
            "requests": requests,
            "input_tokens": tokens,
            "blocked_reason": str(blocked[0]) if blocked else None,
            "resets_at": "00:00 UTC",
            "scope": "This ledger only; Cloudflare's account allocation is shared "
            "with other usage.",
        }
