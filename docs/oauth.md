# Link Cloudflare with OAuth

`clef-browser login` uses Cloudflare's Authorization Code flow with S256 PKCE.
It opens **ordinary Safari** for Cloudflare sign-in and consent, then receives a
one-use callback on this Mac. Browsing tasks still use Safari's native automation
window. These two sessions serve different purposes.

## Register a client once

In your Cloudflare account, open **Manage account → OAuth clients → Create client**.

| Setting | Value |
| --- | --- |
| Name | Clef Safari Browser OAuth |
| Response type | Code |
| Grant types | Authorization Code and Refresh Token |
| Token authentication method | None (PKCE) |
| Redirect URL | `http://127.0.0.1:8766/oauth/callback` |
| Permissions | Workers AI Read and Write (Edit in selection), plus Account Analytics Read for credit tracking |
| Visibility | Private for your account's members |

**Press Return after entering the redirect URL** to add it to the URL list.
All required Workers AI permissions should remain required. Account Analytics Read
enables account-wide neuron tracking and permits reading other account analytics;
the app only queries Workers AI usage. See [credits.md](credits.md). Do not select unrelated
account, DNS, Worker deployment or billing permissions. Refresh requires the
`offline_access` identity scope; the login command requests it automatically. If
your registration lets you edit identity scopes, include it there too.

Save the **public Client ID**. No client secret is used or stored. The Cloudflare
dashboard's client scope details were verified to show **`ai.read` and `ai.write`**
for Workers AI Read/Write, plus `offline_access` for refresh (October 7, 2026).
Use these OAuth IDs, not API-token permission UUIDs. Recheck your registration or
Cloudflare's authenticated `GET /client/v4/oauth/scopes` catalog if permissions change.

Set the non-secret registration information in `.env`:

```dotenv
CLOUDFLARE_ACCOUNT_ID=your-32-character-account-id
CLOUDFLARE_OAUTH_CLIENT_ID=your-public-client-id
CLOUDFLARE_OAUTH_SCOPES=ai.read ai.write account-analytics.read
```

Leave `CLOUDFLARE_AUTH_TOKEN` unset or blank for OAuth. An explicitly configured
API token takes precedence for `run`, `serve`, `doctor`, `credits` and `auth-status`.

```sh
uv run clef-browser login
uv run clef-browser auth-status
uv run clef-browser credits
uv run clef-browser doctor --cloudflare
```

Select the **same account ID** on Cloudflare's consent screen. This version requires
an explicit account ID so it does not request account-list access. `auth-status`
reports a saved connection; only `doctor --cloudflare` verifies Workers AI inference.
The probe uses the existing budget. Login and refresh do not call an AI model.
The `credits` check also makes no inference. Existing clients with only Workers AI
permissions can keep browsing; add Account Analytics Read and relink for usage totals.

The CLI also accepts `login --client-id ... --account-id ... --scope ... --scope ...`.
Use `--port` only with an identically registered callback URL. A busy callback port
stops login. Canceling, denying, or timing out does not replace an existing connection.

## Storage and lifetime

Access and refresh tokens are stored in **macOS Keychain**, in an item owned by this
app and scoped to the absolute `CLEF_STATE_DIR`. The app uses native Security.framework
APIs with explicit byte lengths, avoiding shell commands and command-buffer limits.
Keychain access follows the current macOS user and Python runtime identity; this CLI
does not provide the isolation of a separately signed desktop app. A non-secret `connection.json`
holds registration metadata in the state directory. No token is written to `.env`,
the repo, logs, model state or browser page state.

CLI and MCP load that same connection and refresh tokens within 60 seconds of expiry.
Refreshes serialize across processes; a concurrent OAuth operation fails with an
actionable message. A configured account that differs from the linked account is
refused. Keep the state directory consistent to preserve both linking and accounting.

```sh
uv run clef-browser logout
```

Logout revokes the refresh token and removes this app's Keychain entry and connection
metadata. It preserves the free-tier usage ledger. If remote revocation fails, logout
reports the failure and retains the connection so you can retry. You can also revoke
the application under Cloudflare **My Profile → Manage OAuth authorizations**.

## Sharing the app

Each account can register its own private client. A publisher-provided client that
any Cloudflare user can authorize requires public visibility, branding and verified
ownership of the client URL domain. Making a client public is permanent according to
Cloudflare's docs. The repository does not publish your registration by default.

OAuth authorizes Cloudflare resource access; it does not change Workers Free, the
model selection, the daily allowance, or this application's conservative ledger.

Sources: [client registration](https://developers.cloudflare.com/fundamentals/oauth/create-an-oauth-client/),
[integration endpoints](https://developers.cloudflare.com/fundamentals/oauth/integrate-with-cloudflare/),
[authorization management](https://developers.cloudflare.com/fundamentals/oauth/authorizing-an-application/).
