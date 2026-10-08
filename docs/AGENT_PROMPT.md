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

If Cloudflare credentials are missing, tell me how to create an account-scoped Workers
AI token using Cloudflare's prefilled template (manual tokens need Read and Edit),
and set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_AUTH_TOKEN locally in .env.
Never ask me to paste a token into chat or expose it in output. Keep Workers Free as
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
