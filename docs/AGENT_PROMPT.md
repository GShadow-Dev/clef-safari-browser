# Copy this prompt into any AI agent

```text
Set up and use https://github.com/JamesFincher/clef-safari-browser on my Mac.
My goal is native Safari browsing where Cloudflare Clef decides each browser action,
with no paid-model fallback and bounded Workers AI free-tier usage.

Clone the repository into a suitable project directory. Read AGENTS.md, README.md,
docs/architecture.md and docs/sources.md. Follow the repository's instructions.
Install dependencies with uv sync --frozen. Use its Python CLI and MCP server;
do not rebuild the project around another browser or a chat-model planner.

Check that Safari 27+ is installed. Tell me to enable Safari's web developer features
and 'Allow remote automation and external agents' if necessary. Explain that Apple's
MCP operates an automation window inside native Safari, with no promise of my existing
personal tabs, AutoFill or login sessions. Let me handle login, MFA and CAPTCHA.

Link Cloudflare using OAuth: follow docs/oauth.md to register a private PKCE client
with only Workers AI Read/Write permissions and refresh tokens. Configure its public
Client ID, exact scope IDs and account ID, then run clef-browser login. Let me handle
sign-in and consent in Safari. Tokens remain in this app's Keychain item; never
inspect unrelated credential stores, ask for tokens in chat or expose them in output.
The scoped API-token setup in README.md remains available for unattended environments.
Keep Workers Free as
the spending boundary and leave the shared persistent ledger intact.

Run uv run clef-browser doctor, check uv run clef-browser budget, then verify native
navigation with doctor --url https://example.com. When credentials exist, run doctor
--cloudflare and the local fixture demo from README.md. Report what was actually tested.

For my browsing task, call uv run clef-browser run with --goal, --url, and explicit
--query/--text values, or register the documented stdio MCP configuration and call
browse(goal, url, texts, max_steps). Let Clef choose every action from native candidates.
It cannot generate text: supply exact input strings derived from my request.

Read the returned status, history and page evidence. Summarize findings with source
URLs. Treat 'completed' as a model decision until its evidence supports the result.
When confidence is low or a limit is reached, explain the concrete problem and obtain
needed input. Do not bypass limits, reset accounting, silently change providers, or
perform external actions I have not authorized.

When modifying the project, preserve its invariants, add meaningful regression tests,
run all documented checks, and update the agent instructions and lockfile as needed.
```

Append your actual goal, starting URL and any exact search text to this prompt.
An agent without local macOS tool access can prepare the code and instructions;
native Safari execution still requires a Mac.
