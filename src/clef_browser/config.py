"""Local configuration; Cloudflare credentials never become page/model state."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .budget import RATES


@dataclass(frozen=True)
class Settings:
    account_id: str = ""
    token: str = field(default="", repr=False)
    state_dir: Path = field(
        default_factory=lambda: Path.home() / "Library/Application Support/clef-safari-browser"
    )
    driver: str = "/usr/bin/safaridriver"
    model: str = "clef-flash"
    daily_neurons: float = 8000
    max_steps: int = 24
    page_chars: int = 6000
    candidate_limit: int = 48
    escalate: bool = True

    def __post_init__(self) -> None:
        if self.model not in RATES:
            raise ValueError("CLEF_MODEL must be clef-flash or clef.")
        if not math.isfinite(self.daily_neurons) or not 0 < self.daily_neurons <= 10000:
            raise ValueError("Daily budget must be between 0 and 10,000 neurons.")
        if not 1 <= self.max_steps <= 64:
            raise ValueError("Maximum steps must be between 1 and 64.")
        if not 500 <= self.page_chars <= 8000 or not 5 <= self.candidate_limit <= 128:
            raise ValueError("Page/candidate limits are outside supported bounds.")

    @classmethod
    def from_env(cls, env_file: str | None = None) -> Settings:
        load_dotenv(env_file or Path.cwd() / ".env", override=False)
        base = cls()
        escalate = os.environ.get("CLEF_ESCALATE", "true").lower()
        if escalate not in {"true", "false"}:
            raise ValueError("CLEF_ESCALATE must be true or false.")
        return cls(
            account_id=os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
            token=os.environ.get(
                "CLOUDFLARE_AUTH_TOKEN", os.environ.get("CLOUDFLARE_API_TOKEN", "")
            ),
            state_dir=Path(os.environ.get("CLEF_STATE_DIR", str(base.state_dir))).expanduser(),
            driver=os.environ.get("SAFARI_DRIVER", base.driver),
            model=os.environ.get("CLEF_MODEL", base.model),
            daily_neurons=float(os.environ.get("CLEF_DAILY_NEURONS", "8000")),
            max_steps=int(os.environ.get("CLEF_MAX_STEPS", "24")),
            escalate=escalate == "true",
        )
