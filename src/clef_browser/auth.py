"""Explicit OAuth account linking and request-time refresh shared by CLI and MCP."""

from __future__ import annotations

import fcntl
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .auth_store import KeychainStore, TokenStore
from .budget import Budget
from .clef import ClefClient
from .config import Settings
from .oauth import (
    CallbackListener,
    OAuthClient,
    OAuthConfig,
    OAuthError,
    authorization,
    open_safari,
)


@contextmanager
def auth_lock(state_dir: Path) -> Iterator[None]:
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / "oauth.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise OAuthError(
                "Another OAuth operation is running; retry after it finishes."
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class OAuthAuth:
    def __init__(
        self,
        state_dir: Path,
        store: TokenStore,
        client: OAuthClient | None = None,
        account_id: str = "",
    ) -> None:
        self.state_dir, self.store = state_dir, store
        self.client, self.account_id = client or OAuthClient(), account_id

    async def token(self) -> str:
        with auth_lock(self.state_dir):
            record = self.store.load()
            if record is None:
                raise OAuthError("No linked Cloudflare account. Run clef-browser login.")
            if self.account_id and self.account_id != record.config.account_id:
                raise OAuthError(
                    "Configured account differs from the OAuth account. Run login for that account."
                )
            if record.expires_at <= time.time() + 60:
                record = await self.client.refresh(record)
                self.store.save(record)
            return record.access_token


async def client_for(settings: Settings, budget: Budget) -> ClefClient:
    if settings.token:
        return ClefClient(settings.account_id, settings.token, budget)
    store = KeychainStore(settings.state_dir)
    record = store.load()
    if record is None:
        raise OAuthError(
            "Set CLOUDFLARE_ACCOUNT_ID and use clef-browser login to link Cloudflare, "
            "or set CLOUDFLARE_AUTH_TOKEN locally."
        )
    auth = OAuthAuth(
        settings.state_dir, store, account_id=settings.account_id or record.config.account_id
    )
    token = await auth.token()
    return ClefClient(record.config.account_id, token, budget, get_token=auth.token)


def auth_status(settings: Settings) -> dict[str, Any]:
    if settings.token:
        return {
            "status": "configured",
            "method": "api_token",
            "account_id": settings.account_id,
            "live_verified": False,
        }
    record = KeychainStore(settings.state_dir).load()
    if record is None:
        return {"status": "unlinked", "method": "oauth", "live_verified": False}
    return {
        "status": "linked",
        "method": "oauth",
        "account_id": record.config.account_id,
        "client_id": record.config.client_id,
        "scopes": record.config.scopes,
        "expires_at": record.expires_at,
        "refresh_available": True,
        "live_verified": False,
    }


async def login(settings: Settings, config: OAuthConfig) -> dict[str, Any]:
    store = KeychainStore(settings.state_dir)
    with auth_lock(settings.state_dir):
        url, state, verifier = authorization(config)
        async with CallbackListener(state, config.port) as listener:
            await open_safari(url)
            code = await listener.wait()
            record = await OAuthClient().exchange(config, code, verifier)
            store.save(record)
    return auth_status(Settings(state_dir=settings.state_dir))


async def logout(settings: Settings) -> dict[str, Any]:
    with auth_lock(settings.state_dir):
        store = KeychainStore(settings.state_dir)
        record = store.load()
        if record is not None:
            await OAuthClient().revoke(record)
            store.delete()
    return {
        "status": "unlinked",
        "message": "OAuth connection revoked and removed. Local budget retained.",
    }
