# Troubleshooting

| Symptom | Next step |
| --- | --- |
| MCP tools list, but opening a page times out | Enable Safari Settings → Developer → Allow remote automation and external agents. Re-run doctor with --url. |
| Safari driver is missing or too old | Install Safari 27+; check /usr/bin/safaridriver --version. |
| Another session is running | Finish the other Clef run. Use the same state directory. Do not kill unrelated processes. |
| Credentials are missing | Use Cloudflare's Workers AI token template and set it locally with the account ID; run doctor --cloudflare. |
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
