# Initial validation — October 7, 2026

Development environment: macOS, Python 3.12.13, Safari 27.0 (22625.1.24.11.2).

| Check | Observed result |
| --- | --- |
| Offline test suite | 47 passed; two opt-in native tests skipped |
| Native Safari integration | Two passed: real read/type/click and scrolling to evidence beyond the initial viewport |
| MCP stdio integration | Server startup, tool discovery, budget read and invalid-URL handling passed |
| CLI doctor with local fixture URL | Native navigation verified; Cloudflare credentials absent |
| Ruff lint and formatting | Passed |
| Mypy | Passed across all nine source files |
| Package build | Source distribution and wheel built |
| Gitleaks staged/history scans | No leaks found |
| Independent code review | Four behavioral findings fixed with regressions; no remaining blocker |

Current hosted checks are visible in [GitHub Actions](https://github.com/JamesFincher/clef-safari-browser/actions).

**Not verified:** live Clef inference, confidence calibration on a browsing benchmark,
or authenticated third-party website tasks. Cloudflare credentials were not available
on the development Mac. Run `uv run clef-browser doctor --cloudflare` and the fixture
demo after local credential setup. Native Safari tests use no Cloudflare allocation.

Free-tier accounting bounds this app's local calls. It cannot measure other devices'
or applications' usage of the same Cloudflare account. Keep Workers Free as the
spending boundary and monitor the account dashboard.

## OAuth update — October 7, 2026 (October 8 UTC)

- 65 offline tests passed; two opt-in native tests skipped in that run.
- Both live native Safari read/type/click and viewport-scroll tests passed.
- Cloudflare private PKCE client registration and actual OAuth account linking passed.
  Registered permissions were Workers AI Read (`ai.read`), Write (`ai.write`) and
  `offline_access`; no client secret is needed.
- Native Security.framework Keychain create/read/update/delete passed with a large
  disposable record. Real credentials remained in the app's own scoped item.
- Live refresh-token exchange and persistence passed; the refreshed access token was
  used for subsequent Clef inference. No token values were printed or saved to files.
- `doctor --cloudflare` verified live Clef-flash inference through OAuth.
- A complete live fixture task succeeded: Clef chose the Agent guide link, native
  Safari clicked it, and returned page evidence reported fixture version 1.0.
- A public-web task succeeded: Clef-flash selected the Workers AI pricing link from
  Cloudflare's model index, Safari navigated to the real pricing page, and returned
  its title, URL and visible evidence. An uncertain intermediate decision escalated
  within the existing budget.
- A real stdio MCP client discovered `browse` and `usage`, invoked `browse` through
  a separate server process, loaded the saved OAuth connection, and completed the
  fixture task with version 1.0 evidence.
- A Cloudflare model-catalog task stopped with `needs_input` because both Clef-flash
  and Clef lacked sufficient confidence on the large initial navigation tree. This is
  an observed task-completion limitation, not an authentication failure.
- An example.com test goal referencing a Learn more link stopped rather than finish
  without evidence; that live page contained no such link. Test goals must match
  available page content.
- Ruff, formatting, Mypy across 12 source modules, and wheel/source builds passed.
- An initial Linux CI type check could not infer the guarded native-library fields.
  Explicit library type declarations fixed it; Linux and Darwin type checks both
  passed locally. CI now checks both platform branches.
- Independent review identified the Keychain CLI command-size limit, runtime access
  documentation and non-ASCII callback handling. All were fixed and reviewed again;
  no remaining release blocker was found.
- The tests and probes reserved 1,249 neurons in the shared local ledger across 11
  inference requests, within its unchanged 8,000-neuron daily ceiling. Actual account
  usage by other applications remains outside this ledger.

Tests establish working OAuth and native browsing on this Mac, not general browser
benchmark reliability or an account-wide spending guarantee. The ledger remains
conservative and includes probes, failed/uncertain inference and full-Clef escalation.

## Account neuron tracking — October 8, 2026

- 88 offline tests passed; two opt-in native tests skipped. The 23 added cases cover
  account selection, UTC boundaries, full-account aggregation, exhausted allowance,
  safe authorization/transport errors, invalid/missing/partial data, and actual
  CLI/MCP reports that leave existing reservations unchanged.
- Live GraphQL schema introspection confirmed `aiInferenceAdaptiveGroups` and
  `sum.totalNeurons`, including the required non-null filter argument. A regression
  rejects the invalid nullable query before accepting its corrected form.
- Cloudflare's authenticated scope catalog confirmed `account-analytics.read`.
  The existing Workers AI-only OAuth connection returned `authz`. The live `credits`
  command reported `unavailable`, preserved the ledger and did not present a balance.
- Ruff lint/format, Linux and Darwin Mypy, source/wheel builds and staged/history
  Gitleaks checks passed. Independent review caught the filter declaration, which
  was corrected; no further material defect was identified.

Successful live account totals remain **pending Account Analytics Read permission
and new OAuth consent**. Offline fixtures verify report behavior, not actual billing
accuracy. No model inference or native browser action is needed for a credit check.
