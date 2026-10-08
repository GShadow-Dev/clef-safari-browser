"""Only this app's OAuth item in macOS Keychain; no token files or secret argv."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from .oauth import OAuthConfig, OAuthError, OAuthRecord


class TokenStore(Protocol):
    def load(self) -> OAuthRecord | None: ...
    def save(self, record: OAuthRecord) -> None: ...


class NativeKeychain:
    """Length-delimited native APIs; creator access follows the Python runtime identity."""

    # Linux type checking cannot infer assignments beyond the macOS runtime guard.
    security: ctypes.CDLL
    core: ctypes.CDLL

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise OAuthError("OAuth login requires macOS Keychain.")
        self.security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self.core = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        pointer, uint = ctypes.c_void_p, ctypes.c_uint32
        self.security.SecKeychainFindGenericPassword.argtypes = [
            pointer,
            uint,
            ctypes.c_char_p,
            uint,
            ctypes.c_char_p,
            ctypes.POINTER(uint),
            ctypes.POINTER(pointer),
            ctypes.POINTER(pointer),
        ]
        self.security.SecKeychainAddGenericPassword.argtypes = [
            pointer,
            uint,
            ctypes.c_char_p,
            uint,
            ctypes.c_char_p,
            uint,
            ctypes.c_char_p,
            ctypes.POINTER(pointer),
        ]
        self.security.SecKeychainItemModifyAttributesAndData.argtypes = [
            pointer,
            pointer,
            uint,
            ctypes.c_char_p,
        ]
        self.security.SecKeychainItemDelete.argtypes = [pointer]
        self.security.SecKeychainItemFreeContent.argtypes = [pointer, pointer]
        self.core.CFRelease.argtypes = [pointer]
        self.core.CFRelease.restype = None
        for name in (
            "SecKeychainFindGenericPassword",
            "SecKeychainAddGenericPassword",
            "SecKeychainItemModifyAttributesAndData",
            "SecKeychainItemDelete",
            "SecKeychainItemFreeContent",
        ):
            getattr(self.security, name).restype = ctypes.c_int32

    @staticmethod
    def check(status: int) -> None:
        if status != 0:
            raise OAuthError(
                f"macOS Keychain operation failed (OSStatus {status}). "
                "Unlock your login keychain and allow this Python runtime's access."
            )

    def get(self, service: str) -> bytes | None:
        name, account = service.encode(), b"oauth-session"
        size, data = ctypes.c_uint32(), ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(
            None,
            len(name),
            name,
            len(account),
            account,
            ctypes.byref(size),
            ctypes.byref(data),
            None,
        )
        if status == -25300:  # errSecItemNotFound
            return None
        self.check(status)
        try:
            return ctypes.string_at(data, size.value)
        finally:
            self.security.SecKeychainItemFreeContent(None, data)

    def set(self, service: str, data: bytes) -> None:
        name, account = service.encode(), b"oauth-session"
        item = ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(
            None,
            len(name),
            name,
            len(account),
            account,
            None,
            None,
            ctypes.byref(item),
        )
        if status == -25300:
            self.check(
                self.security.SecKeychainAddGenericPassword(
                    None,
                    len(name),
                    name,
                    len(account),
                    account,
                    len(data),
                    data,
                    None,
                )
            )
            return
        self.check(status)
        try:
            self.check(
                self.security.SecKeychainItemModifyAttributesAndData(
                    item,
                    None,
                    len(data),
                    data,
                )
            )
        finally:
            self.core.CFRelease(item)

    def delete(self, service: str) -> None:
        name, account = service.encode(), b"oauth-session"
        item = ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(
            None,
            len(name),
            name,
            len(account),
            account,
            None,
            None,
            ctypes.byref(item),
        )
        if status == -25300:
            return
        self.check(status)
        try:
            self.check(self.security.SecKeychainItemDelete(item))
        finally:
            self.core.CFRelease(item)


class KeychainStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        digest = hashlib.sha256(str(state_dir.resolve()).encode()).hexdigest()[:24]
        self.service = f"clef-safari-browser.oauth.{digest}"
        self.manifest = state_dir / "connection.json"

    def load(self) -> OAuthRecord | None:
        if not self.manifest.exists():
            return None
        encoded = NativeKeychain().get(self.service)
        if encoded is None:
            raise OAuthError(
                "OAuth Keychain item is unavailable. Unlock your keychain or run login again."
            )
        try:
            data = json.loads(base64.b64decode(encoded, validate=True))
            config = data["config"]
            return OAuthRecord(
                OAuthConfig(
                    config["client_id"],
                    config["account_id"],
                    tuple(config["scopes"]),
                    config["port"],
                ),
                data["access_token"],
                data["refresh_token"],
                float(data["expires_at"]),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise OAuthError(
                "This app's saved OAuth connection is invalid. Run login again."
            ) from exc

    def save(self, record: OAuthRecord) -> None:
        encoded = base64.b64encode(json.dumps(asdict(record), allow_nan=False).encode())
        NativeKeychain().set(self.service, encoded)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temp = self.state_dir / "connection.json.tmp"
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(asdict(record.config), output)
        temp.replace(self.manifest)

    def delete(self) -> None:
        NativeKeychain().delete(self.service)
        self.manifest.unlink(missing_ok=True)
