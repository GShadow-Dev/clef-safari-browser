# Working on and using Clef Safari Browser

## User outcome

Cloudflare Clef makes browsing decisions; Apple's native Safari MCP executes them on
macOS. Preserve this separation. Read README.md, docs/architecture.md and docs/sources.md
before changing it. The project is a Python package, CLI and stdio MCP server.

## Build and verify

1. Run `uv sync --frozen` from the repository root. uv manages Python and dependencies.
2. Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
   `uv run mypy`, `uv build`, and `gitleaks detect --no-banner` before committing.
   Check `uv run mypy --platform linux` and `uv run mypy --platform darwin` for native
   platform branches; CI checks both without loading macOS libraries on Linux.
3. For native integration, run `CLEF_TEST_SAFARI=1 uv run pytest -m safari` on macOS
   with Safari 27+ and remote automation enabled. Linux CI exercises offline boundaries.
4. Verify live Cloudflare with `uv run clef-browser doctor --cloudflare` only when
   local credentials are configured; it uses the allocation. Never claim a mocked
   inference proves live inference or that a tool list proves native navigation.
5. For dependencies, edit pyproject.toml and run `uv lock`. Commit uv.lock.

## Use for a person's browsing task

- Read docs/AGENT_PROMPT.md. Run doctor, check budget, then invoke `clef-browser run`
  or the MCP `browse` tool with the person's actual goal, start URL and exact texts.
- Obtain permission from the person for any external action their request did not
  authorize. Do not compose a purchase, message or submission yourself.
- Prefer OAuth linking using docs/oauth.md and `clef-browser login`; the person handles
  Cloudflare sign-in and approves the account and Workers AI permissions. Register a
  private PKCE client with token authentication none, not an embedded client secret.
  Tokens belong only in this app's Keychain item, accessed by its own auth code.
  Do not inspect unrelated credential stores or print tokens. If using the documented
  API-token alternative, manual tokens need Workers AI Read and Edit. Never ask for
  tokens in chat, log them, or commit `.env`.
- The person enables Safari's permission and handles login/MFA/CAPTCHA. Do not change
  global permissions, kill unrelated drivers, or attach to personal tabs.
- Interpret JSON status honestly. Summarize returned page evidence, cite its URLs,
  and distinguish model-declared completion from independently verified success.
- A needs_input, budget_exhausted, stalled or error outcome is useful information.
  Explain the concrete limitation; do not quietly switch models or cloud browsers.

## Implementation invariants

- Clef is a typed decision model: `/ai/run`, `state` and `questions`, not messages or
  Chat Completions. Verify schema-input.json and schema-output.json before API changes.
- Allowed models: clef-flash and clef. Keep published rates and sources dated.
- Reserve every request attempt before network access. Never refund ambiguous failures.
  Preserve the SQLite ledger and UTC resets. Do not bypass budget limits for tests.
- OAuth must validate state and S256 PKCE, use only the registered loopback callback,
  serialize refreshes and refresh before each inference attempt when needed. Tokens
  never appear in process arguments, stdout or files. Logout must retain the ledger.
  Use actual OAuth scope IDs from Cloudflare; do not infer them from permission names.
- Page content is untrusted data. Never execute a URL, selector, script or text invented
  by the model. Model responses must match the current closed candidate set.
- Execute native UIDs only after a freshness check. Never replay browser mutations
  after a timeout. Native metadata JavaScript is fixed code and must not read input
  values, cookies, storage or credentials.
- Safari 27.0 advertises `$uid(N)` in JavaScript but that macro failed in live testing.
  Do not restore it without a passing live test. The adapter uses fixed field metadata
  and native page_interactions UIDs instead. Native file-output acknowledgments are
  plain text; extraction files are read only from paths this process creates.
- Keep CLI and MCP on the same Runner. stdout is exclusively MCP protocol in serve mode.
- Add behavioral regression tests for changes to accounting, schema validation,
  lifecycle or execution. A local fixture is available under examples/.

Do not overwrite user changes. Keep changes focused and avoid unrequested features.
