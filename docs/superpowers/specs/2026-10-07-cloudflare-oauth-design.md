# Cloudflare OAuth linking

The user requested browser-based Cloudflare OAuth login, local setup and live tests.
Cloudflare's current third-party OAuth documentation supports Authorization Code
with S256 PKCE for desktop/CLI clients and token endpoint authentication `none`.

The CLI gains login, auth-status and logout. Login opens ordinary Safari for human
consent and receives an exact registered loopback callback. Browsing tasks continue
to use native Safari automation. Random state, fresh PKCE, bounded callback parsing,
strict Host/path checks and one-use responses reject unsolicited callbacks.

The registered client is private and requires only Workers AI Read/Write plus
offline_access for refresh. The dashboard verified the exact IDs ai.read and ai.write.
Client/account IDs and scopes are non-secret configuration. Native Security.framework
stores token pairs in one Keychain item scoped to the absolute state directory; no
token passes through argv, stdout or files. Access follows the current macOS user and
Python runtime, rather than a separately signed application's identity.

CLI and MCP resolve the same credentials. Explicit API tokens take precedence.
Before each inference attempt, OAuth refreshes within 60 seconds of expiration under
a process lock. Account mismatch stops execution. Logout revokes the refresh token
and removes connection metadata and the item while retaining the daily ledger.
Inference accounting, model restrictions and Safari execution safeguards are preserved.

Verification covers forged and malformed callbacks, PKCE freshness, exact form-encoded
exchange, insufficient grants, refresh persistence, oversized records, CLI isolation,
and per-attempt token resolution. Live tests cover actual login, refresh, Keychain
roundtrip, native Safari and budgeted Clef-driven browsing. docs/VALIDATION.md records
both successful tasks and confidence-related limits.
