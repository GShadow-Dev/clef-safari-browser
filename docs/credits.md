# Check free Workers AI neurons

```sh
uv run clef-browser credits
```

The command reads the linked account's Workers AI analytics for **today in UTC**.
It makes no AI inference request and consumes no neurons. The MCP equivalent is
`account_usage()`. It returns both `cloudflare` and `local_budget`:

| Field | Meaning |
| --- | --- |
| `cloudflare.used_neurons` | Cloudflare's reported account total across models and applications |
| `cloudflare.free_allowance_neurons` | Published daily allowance: 10,000 neurons |
| `cloudflare.remaining_free_neurons_estimate` | Allowance minus reported total, clamped at zero |
| `cloudflare.used_percent` | Percentage of the daily allowance consumed; can exceed 100 on paid plans |
| `cloudflare.resets_at` | Next midnight in UTC; unused neurons do not carry over |
| `cloudflare.query_start` / `query_end` | Requested time window, not a guarantee that ingestion is current |
| `cloudflare.checked_at` | Time the response was checked |
| `local_budget` | This app's conservative SQLite reservations, also available offline with `budget` |

Cloudflare's `aiInferenceAdaptiveGroups` dataset can use adaptive sampling and have
ingestion delay. Remaining neurons are an **estimate**, not a real-time billing
balance. `data_status: no_reported_events` means no events were returned yet; it
does not establish that there were no recent requests. The report does not detect
whether the account is on Workers Free or Paid. Verify the plan in the dashboard.
Free neurons are a daily allocation, separate from prepaid AI Gateway credits.

An authorization, network or malformed-data error returns `status: unavailable`,
`cloudflare: null`, a safe explanation and the intact local budget. CLI exit code
is 1 in that case. An unknown balance is never presented as 10,000 remaining.
The report does not change or reduce reservations, and the existing local budget
still enforces every inference attempt. Check credits before and after browsing;
other processes can consume the allocation between checks.

## Enable analytics access

For OAuth, edit the existing private client in **Manage account → OAuth clients**.
Keep its Workers AI Read/Write and refresh permissions, and add **Account Analytics
Read**. Its exact OAuth scope is **`account-analytics.read`**, verified through
Cloudflare's authenticated scope catalog on October 8, 2026. This allows reading
account analytics beyond the Workers AI dataset; the application queries only
Workers AI neuron totals. No billing write or deployment permission is needed.

Set the registered scope IDs in your local `.env`, then relink to consent to the
new read permission:

```dotenv
CLOUDFLARE_OAUTH_SCOPES=ai.read ai.write account-analytics.read
```

```sh
uv run clef-browser login
uv run clef-browser credits
```

Changing the local configuration alone does not expand an existing token's access.
For the API-token alternative, add **Account → Account Analytics → Read**, restricted
to the same account, alongside its Workers AI permissions. Do not paste tokens into
chat. Without this permission, browsing still works and `budget` remains available.

The query uses the account ID, a UTC datetime range and one ungrouped aggregate:
`aiInferenceAdaptiveGroups(limit: 1) { count sum { totalNeurons } }`. It applies no
model, source, beta or success filter, so other applications are included. Any GraphQL
error invalidates the whole result, even if partial data is present.

Sources: [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/),
[GraphQL authentication](https://developers.cloudflare.com/analytics/graphql-api/getting-started/authentication/api-token-auth/),
[schema introspection](https://developers.cloudflare.com/analytics/graphql-api/features/discovery/introspection/),
[sampling](https://developers.cloudflare.com/analytics/graphql-api/sampling/).
