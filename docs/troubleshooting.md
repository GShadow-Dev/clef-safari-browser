# Troubleshooting

| Symptom | Next step |
| --- | --- |
| MCP tools list, but opening a page times out | Enable Safari Settings → Developer → Allow remote automation and external agents. Re-run doctor with --url. |
| Safari driver is missing or too old | Install Safari 27+; check /usr/bin/safaridriver --version. |
| Another session is running | Finish the other Clef run. Use the same state directory. Do not kill unrelated processes. |
| Credentials are missing | Follow docs/oauth.md and run login; then doctor --cloudflare. The scoped API-token alternative is in README.md. |
| credits reports analytics access denied | Add Account Analytics Read (`account-analytics.read`) to the client and local scope list, then relink. API tokens need Account Analytics Read on the same account. See credits.md. |
| credits reports unavailable or delayed totals | Keep the local budget; account balance is unknown or estimated. Retry later or check the dashboard. Never clear the ledger. |
| OAuth client form Continue is disabled | Press Return to add the callback URL to its list, and choose Code, Authorization Code/Refresh Token, and None (PKCE). |
| OAuth callback port busy or timeout | Close the other login, retry, and use the exact registered callback URL. Sign in and consent in ordinary Safari. |
| Keychain unavailable | Unlock your login keychain and allow this app's access. Never paste the saved credential into chat. |
| OAuth refresh failed | Check the client's Refresh Token grant and offline_access scope; run login again. |
| Configured and linked accounts differ | Run login for the intended account. Select the same account during consent. |
| HTTP 401/403 | Check token scope, account ID and Workers Free model access. Do not upgrade automatically. |
| Cloudflare code 3036 | The shared daily allocation is exhausted. Wait until the UTC reset and check other account usage. |
| Temporary capacity failure | The client makes at most three budgeted inference attempts. Retry later if it still fails. |
| Local budget exhausted | Check budget and wait for the UTC reset. Do not delete the ledger to circumvent accounting. |
| needs_input | Refine the goal and exact search text, or handle login/CAPTCHA manually. Low confidence does not cause a guess. |
| stalled | The same action was selected on unchanged state. Use a more direct URL or task. |
| step_limit | Review returned evidence; provide a narrower task before extending the run. |
| Repeated stale state | The page changes during inference. Let it settle, use a less dynamic page, or act manually. |
| Unsupported or ambiguous input | Use a field with a unique label/placeholder. Complex forms and unlabeled controls are outside this version. |

For a clean native test run `CLEF_TEST_SAFARI=1 uv run pytest -m safari`. For a
complete live AI test use the fixture demo in README.md after the Cloudflare probe.
No test requires disabling privacy controls, importing personal browser cookies,
or changing system automation settings programmatically.
