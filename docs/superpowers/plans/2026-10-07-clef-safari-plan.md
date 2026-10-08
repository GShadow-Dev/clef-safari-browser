# Clef Safari Browser implementation plan

**Goal:** A working native Safari browser agent driven by Cloudflare Clef with free-tier limits.

**Architecture:** Python CLI and MCP server share one decision loop. Safari uses Apple's
native stdio server through the official MCP SDK. Clef receives bounded closed choices.

**Spec:** [Design](../specs/2026-10-07-clef-safari-design.md)

## Global constraints

Python >=3.11, macOS with Safari >=27. No cloud browser, no deployed Worker, no
generated actions, no paid-model fallback. UTC-day budget 8,000 neurons, 24 steps,
24,000 request bytes, 48 candidates, 6,000 page characters. Never commit credentials.

## Tasks

- [ ] Budget and configuration (`config.py`, `budget.py`, `tests/test_budget.py`):
  write failing tests for reservation persistence, concurrency, rollover, quota failure,
  and usage exceeding reservations; implement transactional SQLite accounting.
- [ ] Clef adapter (`clef.py`, `tests/test_clef.py`): failing tests pin native choice/noul
  envelopes, model selectors, strict probability validation, retry limits, auth/quota
  handling, oversized requests, and reservation-before-network ordering; implement httpx adapter.
- [ ] Safari (`safari.py`, `actions.py`, `tests/test_actions.py`, `tests/test_safari.py`):
  test native textTree UIDs, input candidates, stale state, unsupported schemes,
  credential fields, MCP payloads; use official SDK with bounded waits and own extraction files.
- [ ] Loop and interfaces (`runner.py`, `cli.py`, `server.py`, `tests/test_runner.py`):
  test successful multi-page evidence, low confidence, escalation, stale observations,
  action failures, false completion, repeated no-progress, and maximum steps. Implement
  CLI JSON output and stdio MCP tools over the same runner.
- [ ] Handoff and verification: README, AGENTS.md, agent prompt, architecture, sources,
  configuration example, local fixture, CI and license. Run offline suite, lint, types,
  build, secret scan, and real Safari fixture. Create private GitHub repository and push.

## Review focus

Malformed or non-finite probabilities; ambiguous HTTP failures consuming allocation;
cross-process reservations; DOM changes between decision and execution; Safari extraction
written to disk. Each has a test in the corresponding adapter or loop suite.

## Verification commands

`uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy`, `uv build`, `gitleaks detect --no-banner`, and
`CLEF_TEST_SAFARI=1 uv run pytest -m safari`.
