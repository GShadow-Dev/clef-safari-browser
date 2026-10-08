"""Cloudflare's public-client Authorization Code + S256 PKCE protocol."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import math
import re
import secrets
import time
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

AUTH_URL = "https://dash.cloudflare.com/oauth2/auth"
TOKEN_URL = "https://dash.cloudflare.com/oauth2/token"
REVOKE_URL = "https://dash.cloudflare.com/oauth2/revoke"


class OAuthError(RuntimeError):
    """Actionable authentication error with no codes, tokens or provider response body."""


@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    account_id: str
    scopes: tuple[str, ...]
    port: int = 8766

    def __post_init__(self) -> None:
        if not self.client_id or not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", self.client_id):
            raise OAuthError("Set the public CLOUDFLARE_OAUTH_CLIENT_ID from your registration.")
        if not re.fullmatch(r"[0-9a-fA-F]{32}", self.account_id):
            raise OAuthError("CLOUDFLARE_ACCOUNT_ID must be the 32-character account ID.")
        if not self.scopes or any(
            not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", s) for s in self.scopes
        ):
            raise OAuthError("Set CLOUDFLARE_OAUTH_SCOPES to the registered Workers AI scope IDs.")
        if not 1024 <= self.port <= 65535:
            raise OAuthError("OAuth callback port must be between 1024 and 65535.")

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.port}/oauth/callback"


@dataclass(frozen=True)
class OAuthRecord:
    config: OAuthConfig
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: float


def authorization(config: OAuthConfig) -> tuple[str, str, str]:
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    scopes = list(dict.fromkeys((*config.scopes, "offline_access")))
    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTH_URL}?{query}", state, verifier


def callback_code(target: str, expected_state: str) -> str | None:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.path != "/oauth/callback":
        return None
    try:
        params = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=20)
    except ValueError:
        return None
    state = params.get("state", [])
    if (
        len(state) != 1
        or not state[0].isascii()
        or not secrets.compare_digest(state[0], expected_state)
    ):
        return None
    if "error" in params:
        raise OAuthError("Cloudflare authorization was denied. Run login again when ready.")
    codes = params.get("code", [])
    if len(codes) != 1 or not codes[0] or len(codes[0]) > 4096:
        return None
    return codes[0]


class CallbackListener:
    """One-use local callback. Invalid requests never consume the legitimate login."""

    def __init__(self, state: str, port: int = 8766) -> None:
        self.state, self.port = state, port
        self.server: asyncio.Server | None = None
        self.result: asyncio.Future[str] | None = None

    async def __aenter__(self) -> CallbackListener:
        self.result = asyncio.get_running_loop().create_future()
        try:
            self.server = await asyncio.start_server(
                self._handle, "127.0.0.1", self.port, limit=8192
            )
        except OSError as exc:
            raise OAuthError(
                "OAuth callback port is busy. Close the other login or use --port."
            ) from exc
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        if self.result and not self.result.done():
            self.result.cancel()

    async def wait(self, seconds: float = 180) -> str:
        assert self.result is not None
        try:
            return await asyncio.wait_for(asyncio.shield(self.result), seconds)
        except TimeoutError as exc:
            raise OAuthError("Cloudflare login timed out. Run login again.") from exc

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        status, message = (
            400,
            "Invalid OAuth callback. Return to the Cloudflare authorization page.",
        )
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            lines = raw.decode("ascii").split("\r\n")
            method, target, version = lines[0].split(" ")
            hosts = [line[5:].strip() for line in lines[1:] if line.lower().startswith("host:")]
            if method == "GET" and version == "HTTP/1.1" and hosts == [f"127.0.0.1:{self.port}"]:
                code = callback_code(target, self.state)
                if code and self.result and not self.result.done():
                    self.result.set_result(code)
                    status, message = (
                        200,
                        "Authorization received. Check the terminal for the connection result.",
                    )
        except OAuthError as exc:
            if self.result and not self.result.done():
                self.result.set_exception(exc)
            message = "Cloudflare authorization was denied. You can close this tab."
        except (
            TimeoutError,
            ValueError,
            UnicodeError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            pass
        finally:
            body = message.encode()
            writer.write(
                (
                    f"HTTP/1.1 {status} {'OK' if status == 200 else 'Bad Request'}\r\n"
                    "Content-Type: text/plain; charset=utf-8\r\n"
                    "Cache-Control: no-store\r\nReferrer-Policy: no-referrer\r\n"
                    "Content-Security-Policy: default-src 'none'\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
                ).encode()
                + body
            )
            try:
                await writer.drain()
            except (ConnectionError, OSError):
                pass
            writer.close()
            await writer.wait_closed()


class OAuthClient:
    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        self.http = http

    async def _post(self, url: str, form: dict[str, str]) -> dict[str, Any]:
        try:
            if self.http is None:
                async with httpx.AsyncClient(
                    timeout=30, follow_redirects=False, trust_env=False
                ) as http:
                    response = await http.post(url, data=form)
            else:
                response = await self.http.post(url, data=form, timeout=30)
        except httpx.TransportError as exc:
            raise OAuthError("Cloudflare OAuth network failure; retry login if needed.") from exc
        if not response.is_success:
            raise OAuthError(
                f"Cloudflare OAuth failed (HTTP {response.status_code}). "
                "Check the client configuration or log in again."
            )
        if url == REVOKE_URL:
            return {}
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
            return data
        except ValueError as exc:
            raise OAuthError("Cloudflare OAuth returned an invalid response.") from exc

    def _record(
        self, config: OAuthConfig, data: dict[str, Any], old_refresh: str = ""
    ) -> OAuthRecord:
        access, refresh = data.get("access_token"), data.get("refresh_token", old_refresh)
        if any(
            not isinstance(t, str) or not t or any(ord(c) < 33 or ord(c) > 126 for c in t)
            for t in (access, refresh)
        ):
            raise OAuthError(
                "OAuth tokens are missing or invalid. Enable the refresh_token grant "
                "and offline_access scope on your client."
            )
        seconds = data.get("expires_in")
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds <= 60
        ):
            raise OAuthError("Cloudflare OAuth returned an invalid token lifetime.")
        if str(data.get("token_type", "")).lower() != "bearer":
            raise OAuthError("Cloudflare OAuth returned an unsupported token type.")
        granted = data.get("scope")
        if granted is not None and (
            not isinstance(granted, str) or not set(config.scopes) <= set(granted.split())
        ):
            raise OAuthError("Cloudflare did not grant all configured Workers AI scopes.")
        assert isinstance(access, str) and isinstance(refresh, str)
        return OAuthRecord(config, access, refresh, time.time() + seconds)

    async def exchange(self, config: OAuthConfig, code: str, verifier: str) -> OAuthRecord:
        data = await self._post(
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "client_id": config.client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": config.redirect_uri,
            },
        )
        return self._record(config, data)

    async def refresh(self, record: OAuthRecord) -> OAuthRecord:
        data = await self._post(
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "client_id": record.config.client_id,
                "refresh_token": record.refresh_token,
            },
        )
        return self._record(record.config, data, record.refresh_token)

    async def revoke(self, record: OAuthRecord) -> None:
        await self._post(
            REVOKE_URL,
            {
                "client_id": record.config.client_id,
                "token": record.refresh_token,
                "token_type_hint": "refresh_token",
            },
        )


async def open_safari(url: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "/usr/bin/open",
        "-a",
        "Safari",
        url,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if await process.wait() != 0:
        raise OAuthError("Could not open Safari for Cloudflare login.")
