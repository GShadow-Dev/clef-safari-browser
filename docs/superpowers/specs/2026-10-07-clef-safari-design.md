# Clef Safari Browser design

## Intended outcome

A runnable, GitHub-hosted project lets a person or any MCP-compatible AI agent browse
in native Safari using Cloudflare Clef to choose each next action. It includes
installation, usage, maintenance instructions, and explicit free-tier controls.

## Verified interfaces (October 7, 2026)

Clef launched October 1. `@cf/cloudflare/clef-flash` and `@cf/cloudflare/clef` accept
`model`, `state`, and `questions` at the Workers AI `/ai/run` REST endpoint. Choice
questions accept 2–255 candidates and return `choice`, `probabilities`, `confidence`.
Noul answers contain `noul`. These are decisions, not generated text or tool calls.
Published input rates are 8,182 and 21,818 neurons per million tokens, respectively.
Workers AI includes 10,000 neurons per UTC day across the account. See docs/sources.md.

Safari 27's `/usr/bin/safaridriver --mcp` exposes stdio MCP. Its live tool catalog and
an actual create-tab/content-read call were verified on this Mac. Native `textTree`
contains `uid=N` references. Interactions require `purpose` and `type`; typing uses
`value`, `replaceAll`, and optional `pressReturn`.

## Architecture and choices

A Python 3.11+ package uses the official MCP SDK for Safari and httpx for Clef.
The browser remains local; only bounded page text and candidate descriptions go to
Cloudflare. No Cloudflare Browser Run, remote Chromium, deployment, LLM planner, or
vision inference is required. Apple's MCP controls an automation window in Safari;
ordinary personal tabs, AutoFill, and existing logins are not promised.

The observation → candidates → Clef decision → freshness check → native action loop
uses actual native element IDs. A caller supplies a goal, starting URL, and optional
exact search/input texts. Clef cannot invent text, URLs, selectors, or JavaScript.
The default input text is the goal. Terminal actions and scroll/wait are fixed;
click and type candidates are derived from native interactive elements. Arbitrary
open-ended planning and generated prose answers are outside this first version.
Results include status, visited-page evidence, action history, and budget usage.

## Reliability and spending

Default: Clef-flash, 24 steps maximum, 6,000 page characters, 48 candidates maximum,
24,000 request bytes maximum, and 8,000 reserved neurons per UTC day. A SQLite
ledger reserves before every HTTP attempt, across concurrent processes. A conservative
UTF-8 byte estimate plus schema overhead and 25% headroom is never refunded, including
failures and retries. Returned usage is recorded and anomalies stop subsequent calls.
Only the two Clef models are allowed. One Clef escalation on low confidence is optional;
it stays within the same budget. Bounded retry applies to inference, never browser
actions. Account quota/auth errors stop immediately. Input-only text is the default;
images are refused because their budget cannot be estimated by this ledger.

The ledger guards this app on this Mac, not other apps or devices on the account.
Workers Free is the actual spending boundary; paid accounts can incur overages from
other usage. Pricing is pinned to the date above and must be checked on upgrades.

Fresh observations prevent replaying stale candidates. Unknown choices, malformed
distributions, low confidence, exhausted budgets, repeated unchanged actions, and
unmet completion checks stop with an explicit status. Finishing requires a high
goal-completion probability, and returns source evidence rather than inventing a summary.

## Deliverables and validation

CLI: doctor, run, budget, serve. MCP: browse, usage. Docs: README, AGENTS.md,
agent prompt, sources, architecture, troubleshooting. Tests: real HTTP client with
controlled transport, persistent/concurrent budget behavior, native snapshot parser,
decision loop failure boundaries, and opt-in live Safari fixture interaction. CI runs
formatting, lint, types, offline tests, package build, and secret scanning.
