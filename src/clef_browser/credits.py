"""Account-wide Workers AI analytics, separate from conservative local reservations."""

from __future__ import annotations

import math
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .auth import credentials_for
from .budget import Budget
from .config import Settings
from .oauth import OAuthError

FREE_DAILY_NEURONS = 10000
GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
# No dimensions or model/source filters: one aggregate over the entire account.
USAGE_QUERY = """
query AccountNeurons($accountTag: string!,
    $filter: AccountAiInferenceAdaptiveGroupsFilter_InputObject!) {
  viewer {
    accounts(filter: {accountTag: $accountTag}) {
      accountTag
      aiInferenceAdaptiveGroups(limit: 1, filter: $filter) {
        count
        sum { totalNeurons }
      }
    }
  }
}
"""
PERMISSION_HELP = (
    "Cloudflare analytics access was denied. Add Account Analytics Read "
    "(account-analytics.read) to the OAuth client and relink with clef-browser login; "
    "API tokens need Account Analytics Read for this account. See docs/credits.md."
)


class CreditsError(RuntimeError):
    """Safe failure with no server bodies, credentials or false zero balance."""


def nonnegative_number(value: Any) -> float:
    if type(value) not in {int, float}:
        raise CreditsError("Cloudflare returned invalid neuron usage data.")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise CreditsError("Cloudflare returned invalid neuron usage data.") from exc
    if not math.isfinite(number) or number < 0:
        raise CreditsError("Cloudflare returned invalid neuron usage data.")
    return number


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class CreditsClient:
    def __init__(
        self,
        account_id: str,
        get_token: Callable[[], Awaitable[str]],
        http: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not re.fullmatch(r"[0-9a-fA-F]{32}", account_id):
            raise ValueError("CLOUDFLARE_ACCOUNT_ID must be the 32-character account ID.")
        self.account_id, self.get_token, self.http = account_id, get_token, http
        self.clock = clock or (lambda: datetime.now(UTC))

    async def usage(self) -> dict[str, Any]:
        token = await self.get_token()
        if not token or any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise CreditsError("Cloudflare credentials are invalid. Relink or check local setup.")
        now = self.clock().astimezone(UTC).replace(microsecond=0)
        start = now.replace(hour=0, minute=0, second=0)
        body = {
            "query": USAGE_QUERY,
            "variables": {
                "accountTag": self.account_id,
                "filter": {"datetime_geq": utc_text(start), "datetime_lt": utc_text(now)},
            },
        }
        try:
            if self.http is None:
                async with httpx.AsyncClient(
                    timeout=30, follow_redirects=False, trust_env=False
                ) as http:
                    response = await http.post(
                        GRAPHQL_URL, headers={"Authorization": f"Bearer {token}"}, json=body
                    )
            else:
                response = await self.http.post(
                    GRAPHQL_URL, headers={"Authorization": f"Bearer {token}"}, json=body
                )
        except httpx.HTTPError as exc:
            raise CreditsError(
                "Cloudflare usage check failed; retry when the network is ready."
            ) from exc
        if response.status_code in {401, 403}:
            raise CreditsError(PERMISSION_HELP)
        if response.status_code != 200:
            raise CreditsError(f"Cloudflare usage check failed (HTTP {response.status_code}).")
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise CreditsError("Cloudflare returned malformed analytics data.")
            errors = data.get("errors")
            if errors:
                if isinstance(errors, list) and any(
                    isinstance(error, dict)
                    and isinstance(error.get("extensions"), dict)
                    and error["extensions"].get("code") in {"authz", "authn"}
                    for error in errors
                ):
                    raise CreditsError(PERMISSION_HELP)
                raise CreditsError("Cloudflare could not return account analytics; retry later.")
            accounts = data["data"]["viewer"]["accounts"]
            if not isinstance(accounts, list) or len(accounts) != 1:
                raise CreditsError("Cloudflare did not return the requested account's usage.")
            account = accounts[0]
            if account["accountTag"].lower() != self.account_id.lower():
                raise CreditsError("Cloudflare returned usage for a different account.")
            groups = account["aiInferenceAdaptiveGroups"]
            if not isinstance(groups, list) or len(groups) > 1:
                raise CreditsError("Cloudflare returned an invalid account usage aggregate.")
            neurons = nonnegative_number(groups[0]["sum"]["totalNeurons"]) if groups else 0.0
            requests = nonnegative_number(groups[0]["count"]) if groups else 0.0
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise CreditsError(
                "Cloudflare returned malformed analytics data; usage is unknown."
            ) from exc
        return {
            "account_id": self.account_id,
            "utc_day": start.date().isoformat(),
            "used_neurons": neurons,
            "free_allowance_neurons": FREE_DAILY_NEURONS,
            "remaining_free_neurons_estimate": max(0, FREE_DAILY_NEURONS - neurons),
            "above_free_allowance_neurons": max(0, neurons - FREE_DAILY_NEURONS),
            "used_percent": neurons / FREE_DAILY_NEURONS * 100,
            "requests": requests,
            "resets_at": utc_text(start + timedelta(days=1)),
            "query_start": utc_text(start),
            "query_end": utc_text(now),
            "checked_at": utc_text(self.clock()),
            "source": "Cloudflare GraphQL aiInferenceAdaptiveGroups.sum.totalNeurons",
            "data_status": "reported" if groups else "no_reported_events",
            "is_estimate": True,
            "note": "Account-wide analytics may have ingestion delay and adaptive sampling. "
            "Remaining free neurons are an estimate, not a real-time billing balance. "
            "The allowance renews daily and does not roll over. This does not detect your plan.",
            "dashboard_url": f"https://dash.cloudflare.com/{self.account_id}/ai/workers-ai",
        }


async def credits_report(settings: Settings) -> dict[str, Any]:
    local = Budget(settings.state_dir / "usage.sqlite3", settings.daily_neurons).usage()
    try:
        credentials = credentials_for(settings)
        cloudflare = await CreditsClient(credentials.account_id, credentials.get_token).usage()
    except (CreditsError, OAuthError, ValueError) as exc:
        return {
            "status": "unavailable",
            "message": str(exc),
            "cloudflare": None,
            "local_budget": local,
        }
    return {"status": "ready", "cloudflare": cloudflare, "local_budget": local}
