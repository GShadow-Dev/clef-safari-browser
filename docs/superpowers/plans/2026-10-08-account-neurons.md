# Account neuron tracking

Add `clef-browser credits` and MCP `account_usage()` to read the linked account's
UTC-day Workers AI usage without running a model or opening Safari. Keep `budget`
and MCP `usage()` as the conservative local ledger.

1. Test the HTTP boundary: UTC range, account selection, ungrouped neuron sum,
   remaining allowance clamped at zero, malformed/missing/permission results,
   safe transport errors, and no inference/ledger debit.
2. Share credential resolution in `auth.py`; add `credits.py` using GraphQL
   `aiInferenceAdaptiveGroups { count sum { totalNeurons } }`. Label totals as
   analytics estimates with possible ingestion delay, not billing balances.
3. Expose JSON CLI and MCP reports containing account usage and local budget.
   Test the actual command/tool behavior against controlled HTTP.
4. Update setup, OAuth and agent instructions with Account Analytics Read
   (`account-analytics.read`), verified from the live OAuth scope catalog. Prepare
   the existing client's permission update and obtain action-time confirmation
   before saving broader access, then relink and verify live totals.
5. Run the full suite, Ruff, both platform type checks, build and secret scans;
   request code review, commit, push, and verify GitHub CI.

Evidence: live schema introspection confirms totalNeurons; existing ai.read/ai.write
OAuth token returns GraphQL authz for the usage dataset. No additional scope has
been granted yet. Cloudflare's documented Account Analytics Read permission maps
to the verified OAuth scope. No deployment, paid plan or automation is needed.
