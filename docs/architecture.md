# Architecture

`cli.py` and `server.py` share `Runner` in `runner.py`. One-shot runs use `browse_task()`;
MCP and CLI `session` use `session.py` to retain the same native connection. Its queue
keeps SDK AnyIO scopes in one owning task across different MCP request tasks. Human
handoffs leave the connection open. Concurrent tasks return busy. Cancellation stops
before another browser action; an already dispatched native mutation is never replayed.
`config.py` loads local settings; `budget.py` holds the persistent SQLite ledger.
`clef.py` makes authenticated Workers AI requests and validates typed answers.
`actions.py` extracts native nodes and builds a finite action set.
`safari.py` connects to Apple's native server using the official Python MCP SDK.
`oauth.py` implements Cloudflare PKCE and the loopback callback; `auth_store.py`
owns one state-directory-scoped macOS Keychain item. `auth.py` links/revokes accounts
and resolves credentials for both CLI and MCP, refreshing before inference attempts.
Explicit API tokens take precedence. OAuth failures stop without executing a browser
action; login/logout never clear the daily budget.
`credits.py` shares the credential provider and reads an ungrouped GraphQL Workers
AI neuron aggregate for the current UTC day. CLI `credits` and MCP `account_usage`
combine that account-wide estimate with the separate local ledger, without inference.
Permission failures and malformed/partial results return an unavailable account balance.

The caller supplies a goal, HTTP(S) start URL and up to four exact input texts of up
to 10,000 characters each. Full text values stay local: bounded previews, character
counts and action IDs go to Clef. Exact strings are passed to native typing only.
Runner opens a new automation tab, captures the visible viewport's native textTree into its own temporary
file, and creates click/type/select choices from interactive UIDs. It pins the
returned `page-UUID` handle and reselects that owned tab before reads. Resume keeps
the tab and requires the task URL's origin to match. It adds fixed and container scroll,
wait, stop and finish choices. Input values are redacted from native extraction;
sensitive fields are excluded. Public option values are preserved because Safari
may emit them without a separate label. An active dialog supplies the decision
evidence and candidates; the full extraction still supplies the freshness fingerprint.
Candidate descriptions and page prose remain
untrusted evidence.

One request asks Clef both a next-action choice and a goal-completion noul question.
The client validates the model, answer types, candidate identity, finite probabilities,
distribution sum and consistency of the winner. Execution requires a winning
probability >=0.60, confidence >=0.50 and margin >=0.12. An uncertain Flash result
can be evaluated once by Clef on the same choices. Finish requires completion >=0.85
and unchanged page state. These thresholds are engineering defaults, not calibrated
browser benchmark results.

Before execution the adapter extracts the page again and compares fingerprints,
then uses native `page_interactions`. Typing also checks visible field metadata using
a fixed local script; ambiguous, password, file and payment inputs are refused.
Rich text editors are included; an unlabeled textarea is accepted only when its
visible metadata has a unique match. Typing never submits unless Clef chooses the
separate search-and-Return candidate. Dropdown options must match native extraction
and fixed local public-option metadata. Safari 27.0's `selectMenuItem` omits input/change
events, so a fixed adapter script notifies the uniquely identified select after native
selection. Only observed label metadata is substituted as JSON data, never executable
model text or selectors. No script reads editable values, cookies or storage.
A model never supplies JavaScript.
An MCP tool error stops the action; it is not retried. Stale observations cause a new
decision. An action repeated on identical state stops the loop.

Each inference attempt reserves against the UTC day using `BEGIN IMMEDIATE` before
the HTTP request. Reservations persist after crashes and failures. Model usage is
stored and can increase the charge. Unexpected underestimates persist a per-day block
that also stops subsequent processes. Input estimation uses complete UTF-8 request bytes,
1,024 bytes of overhead and a 1.25 multiplier. Request and model allowlists prevent
unbudgeted vision or arbitrary models. HTTP retry is bounded and each attempt pays
its own reservation. A local file lock prevents simultaneous sessions within the
same state directory; unrelated Safari automation should be stopped by its owner.

Results contain bounded extracts and actual executed/stale action history. They
do not contain generated prose answers. The caller can use a separate agent to
summarize the evidence, without changing which model decided the browser actions.

The local database is not an account-wide quota meter. Keep all clients on the same
state directory, check account totals with `credits` or the dashboard, and use Workers Free if charges
must be impossible. Remote services and dynamic websites remain fallible.
