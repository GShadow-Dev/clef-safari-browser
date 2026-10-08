# Clef Safari Browser

Cloudflare **Clef chooses what to click; native Safari performs the action**.
Run a concrete browsing task from your terminal or let any MCP-compatible AI agent
call the included `browse` tool. The browser runs on your Mac.

```text
Safari page → native element IDs → allowed actions → Clef probabilities
    ↑                                      ↓
    └──── inspect result ← check freshness ← execute one action
```

Uses [Clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/)
by default and optionally escalates an uncertain decision to
[Clef](https://developers.cloudflare.com/workers-ai/models/clef/).
There is no chat model generating selectors, URLs, JavaScript or tool calls.
Cloudflare Browser Run and a deployed Worker are unnecessary.

## Requirements

- macOS with **Safari 27+** and `/usr/bin/safaridriver --mcp`.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for Python and dependencies.
- A Cloudflare account on **Workers Free**, linked through OAuth or a Workers AI API token.
- Network access to Workers AI and the websites you request.

Safari 27's native MCP server controls an **automation window inside Safari**.
It does not attach to arbitrary personal tabs or promise access to their logins or
AutoFill. Sign in manually in that window when necessary. See
[Apple's native MCP announcement](https://webkit.org/blog/18136/introducing-the-safari-mcp-server-for-web-developers/).

## Setup

```sh
git clone https://github.com/JamesFincher/clef-safari-browser.git
cd clef-safari-browser
uv sync --frozen
cp .env.example .env
```

Enable Safari → Settings → Advanced → **Show features for web developers**.
Then enable Settings → Developer → **Allow remote automation and external agents**.
The project checks the driver; it does not change your Safari permissions.

### Link your Cloudflare account with OAuth

Register a private desktop OAuth client with PKCE using [docs/oauth.md](docs/oauth.md).
Set its public Client ID, Workers AI scope IDs and your account ID in `.env`, then:

```sh
uv run clef-browser login
uv run clef-browser auth-status
```

Safari opens Cloudflare's consent screen. Access and refresh tokens stay in this
app's macOS Keychain entry. CLI and MCP automatically use the linked account and
refresh expired tokens. `uv run clef-browser logout` revokes the connection and
retains the usage ledger. No client secret or pasted API token is needed.

### API token alternative

Use Cloudflare's **Workers AI → Use REST API → Create a Workers AI API Token**
template, scoped to your account, following
[Cloudflare's REST setup](https://developers.cloudflare.com/workers-ai/get-started/rest-api/).
If creating the token manually, include **Workers AI Read and Edit** permissions.
Set your 32-character account ID and token in the local `.env`:

```dotenv
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_AUTH_TOKEN=your-workers-ai-token
```

Credentials can also come from environment variables. They never enter model state.
`.env`, the usage database, and run logs are excluded from Git. Keep your token local.
An explicitly configured API token takes precedence over a saved OAuth connection.

### Verify the connection

```sh
uv run clef-browser doctor
uv run clef-browser doctor --url https://example.com
uv run clef-browser doctor --cloudflare
```

The first check validates the native tool catalog. `--url` opens and reads a page; `--cloudflare`
makes one small, budgeted live inference. A working tool list alone does not prove
Safari's remote-automation permission or Cloudflare credentials work.

## Use

```sh
uv run clef-browser run \
  --url https://developers.cloudflare.com/workers-ai/ \
  --goal "Open the Clef-flash model documentation" \
  --query "Clef-flash"
```

`--query` and `--text` are aliases. Repeat up to four times to supply exact text
of up to 10,000 characters each (including multiline lyrics)
that Clef may choose to type. If omitted, the first 1,000 characters of the goal
are the available search text. Clef selects a provided value; it cannot compose one.
Typing replaces the field without submitting. Search fields also offer a separate
type-and-Return choice. Clef can fill rich text editors, textareas and ordinary text
inputs, click checkboxes/radios and visible menu items, select observed dropdown
options, and scroll nested form containers. Submission is a separate click chosen
by Clef. An active dialog takes priority over controls behind it.

For tasks that need sign-in, use the persistent MCP server or `session` command.
One-shot `run` closes its automation connection when it returns. Do not repeatedly
use it across login handoffs.

```sh
uv run clef-browser session
```

Keep that process and its stdin open. Send one JSON task per line, for example:

```json
{"goal":"Open the create form; stop if login is required","url":"https://suno.com/create","max_steps":4}
{"goal":"Fill Lyrics editor using text 0 and Styles using text 1. Do not click Create yet.","url":"https://suno.com/create","texts":["[Verse]\nMy exact lyrics","soul, male vocals"],"resume":true,"max_steps":12}
{"command":"exit"}
```

When `needs_input` requires sign-in, let the person complete it in the automation
tab, then send `resume:true` with the same origin. The worker retains its connection
and the adapter reselects only the task tab it created. Closing stdin, exiting the
MCP client or restarting the worker ends that session; login is not persisted across
process restarts. No cookies are exported. Check the returned evidence after each task.

```sh
uv run clef-browser run --url https://www.wikipedia.org/ \
  --goal "Find the Wikipedia article about Safari and open it" --query Safari

uv run clef-browser run --url https://developers.cloudflare.com/workers-ai/ \
  --goal "Open the pricing page" --model clef --max-steps 12

uv run clef-browser budget
uv run clef-browser credits
```

Runs print JSON with `status`, `visited_urls`, `pages` (up to six page extracts),
`history`, and `budget`. `completed` means Clef selected finish with sufficient
completion probability; inspect the evidence. Clef cannot generate a prose answer.
An AI agent consuming the result can summarize the page extracts and cite their URLs.

Other statuses are `needs_input`, `stalled`, `step_limit`, `budget_exhausted`, and
`error`. CLI exit code is 0 for completed runs and 1 for other outcomes; Ctrl-C exits 130.
Run `uv run clef-browser --help` for commands.

## Give it to any AI agent

Copy [docs/AGENT_PROMPT.md](docs/AGENT_PROMPT.md) into your agent, or tell it:

> Clone this repository, read AGENTS.md and README.md, set it up on my Mac, and use
> Clef to perform my browsing task through native Safari. Follow docs/AGENT_PROMPT.md.

The included [AGENTS.md](AGENTS.md) describes building, testing, maintaining and using
the project without assuming a particular AI vendor.

For any stdio MCP client, replace the absolute paths below:

```json
{
  "mcpServers": {
    "clef-safari-browser": {
      "command": "uv",
      "args": [
        "--directory", "/absolute/path/to/clef-safari-browser",
        "run", "--frozen", "clef-browser",
        "--env-file", "/absolute/path/to/clef-safari-browser/.env", "serve"
      ]
    }
  }
}
```

For Codex:

```sh
codex mcp add clef-safari-browser -- uv \
  --directory /absolute/path/to/clef-safari-browser \
  run --frozen clef-browser \
  --env-file /absolute/path/to/clef-safari-browser/.env serve
```

For Claude Code, substitute `claude` for `codex`. The server exposes:

- `browse(goal, url, texts?, max_steps?, resume?)`: the complete Clef → native Safari
  loop. The MCP connection retains Safari across calls; `resume:true` continues the
  existing task tab after login or a step limit. The start URL's origin must match.
- `usage()`: local daily budget usage without inference.
- `account_usage()`: Cloudflare's account-wide neuron estimate plus the local budget,
  without inference. Requires Account Analytics Read; see [docs/credits.md](docs/credits.md).

Call `browse` with a precise goal and input texts. This lets an agent delegate
browser decisions to Clef; registering Apple's Safari MCP alone would leave those
decisions to the host agent's model.

## Staying within the free tier

[Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
was checked October 7, 2026. The account receives 10,000 neurons per UTC day;
Clef-flash uses 8,182 neurons per million input tokens and Clef uses 21,818.
Both have input-only pricing. Request schemas also consume input tokens.

The default local ceiling is **8,000 reserved neurons/day**, with **24 steps/run**.
Reservations use UTF-8 request bytes plus overhead and 25% headroom, intentionally
overestimating normal text tokenization. A SQLite transaction reserves before every
HTTP attempt, even across processes. Failed requests and retries remain reserved.
Reported usage can increase a reservation, never decrease it. An underestimate
blocks further inference for that UTC day, including new runs. Requests stop at the
budget limit, including escalation; unknown or unrelated models are refused.

Requests contain at most 24,000 bytes, 6,000 page characters and 48 action choices
by default. Images are disabled to keep accounting predictable. Transient inference
errors receive at most three budgeted attempts; account-quota error 3036 stops
immediately. Browser actions are never retried automatically.

The ledger measures **this application on one Mac**, not other apps or devices.
Leave `CLEF_STATE_DIR` consistent across clients and repository copies. Changing or
deleting it discards the application's accounting. The default is
`~/Library/Application Support/clef-safari-browser/usage.sqlite3`.

Check **`uv run clef-browser credits`** before and after tasks to see account neurons
used, estimated remaining free neurons, percentage used and the next UTC reset,
alongside local reservations. It reads Cloudflare's Analytics API and consumes no
neurons. Add Account Analytics Read to your OAuth client and relink once, following
[docs/credits.md](docs/credits.md). Analytics can lag or use sampling, so the estimate
does not replace Workers Free or the local reservation limit. Errors return an unknown
account balance rather than claiming the full free allowance remains.

Use Workers Free as the actual spending boundary. On a paid account, unrelated
usage can exhaust the shared allocation and cause charges despite this app's local
ceiling. No fixed number of daily tasks is promised: page size, uncertainty and
other account usage determine it. Pricing and API behavior can change.

## Development and verification

```sh
uv sync --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
gitleaks detect --no-banner
```

Offline tests exercise the real adapters against controlled HTTP/MCP boundaries.
The native integration test starts a local fixture server and actually reads,
types and clicks in Safari without Cloudflare credentials:

```sh
CLEF_TEST_SAFARI=1 uv run pytest -m safari
```

For a live Clef-driven fixture demo, first serve `examples/` in another terminal:

```sh
uv run python -m http.server 8765 --bind 127.0.0.1 --directory examples
```

Then:

```sh
uv run clef-browser run --url http://127.0.0.1:8765/fixture.html \
  --goal "Open the Agent guide and find the fixture version" --query "Agent guide"
```

Validation: offline tests, types, lint, package build, and three real Safari integration
tests on Safari 27.0. OAuth linking, refresh, native Keychain storage, live Clef-flash
inference, and a complete Clef-driven fixture task were also verified. See
[the validation record](docs/VALIDATION.md) for observed limits. Run
`doctor --cloudflare` and the fixture demo after linking your own account. No general
browser benchmark or guarantee of task completion is claimed.

## Limits and privacy

Visible page text, labels, the goal and supplied input descriptions go to Cloudflare.
Treat authenticated pages as data you are choosing to send there. Password fields
are excluded from candidates, native editable `value=` attributes are redacted (public
select option values remain available), and a fixed
local metadata check refuses credential/payment/file inputs. Redaction does not
remove secrets already visible in page prose. The model cannot run arbitrary code.

Confidence thresholds are guardrails, not proof of correctness. Dynamic pages,
cross-origin frames, ambiguous unlabeled fields, canvas interfaces, CAPTCHAs, logins and
unsupported widgets may require human input. The adapter refreshes before executing
and stops on ambiguity; a site can still change during an individual native action.
Use one Safari automation session at a time. Ordinary personal tabs are not used.
File uploads, OS file pickers and slider values are not yet supported by the closed
action adapter; these return a handoff instead of inventing an action. The Suno album
art upload and complete 18-song workflow have not been verified.

See [architecture](docs/architecture.md), [troubleshooting](docs/troubleshooting.md),
[OAuth linking](docs/oauth.md), and [verified primary sources](docs/sources.md). MIT license.
