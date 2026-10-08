# Verified primary sources

Checked October 7, 2026. Review these on dependency, API or pricing changes.

- [Clef launch, October 1](https://developers.cloudflare.com/changelog/post/2026-10-01-clef-workers-ai/):
  decision-model purpose, typed questions and selectors.
- [Clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/) and
  [Clef](https://developers.cloudflare.com/workers-ai/models/clef/): native request API.
- [Input JSON schema](https://developers.cloudflare.com/workers-ai/models/clef-flash/schema-input.json)
  and [output JSON schema](https://developers.cloudflare.com/workers-ai/models/clef-flash/schema-output.json):
  exact choice/noul envelopes and input-token usage fields.
- [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/):
  account allowance, UTC reset, free/paid behavior and model rates used by budget.py.
- [Workers AI errors](https://developers.cloudflare.com/workers-ai/platform/errors/):
  daily exhaustion 3036, temporary capacity 3040 and access errors.
- [Workers AI REST setup](https://developers.cloudflare.com/workers-ai/get-started/rest-api/):
  account ID and scoped API token instructions.
- [OAuth client registration](https://developers.cloudflare.com/fundamentals/oauth/create-an-oauth-client/):
  public-client S256 PKCE, required scopes, private/public visibility and refresh grants.
- [OAuth integration](https://developers.cloudflare.com/fundamentals/oauth/integrate-with-cloudflare/):
  authorization, token and revocation endpoints. The live OpenID discovery document
  also confirmed those endpoints and token authentication `none`.
- [OAuth authorization management](https://developers.cloudflare.com/fundamentals/oauth/authorizing-an-application/):
  account selection, consent and dashboard revocation.
- [WebKit's Safari MCP announcement](https://webkit.org/blog/18136/introducing-the-safari-mcp-server-for-web-developers/):
  native server, prerequisites, tools and personal-data limitations.
- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk):
  stdio client, ClientSession and FastMCP.

## Direct native observations

Account tracking checked October 8, 2026:
[GraphQL token permissions](https://developers.cloudflare.com/analytics/graphql-api/getting-started/authentication/api-token-auth/),
[introspection](https://developers.cloudflare.com/analytics/graphql-api/features/discovery/introspection/),
and [sampling](https://developers.cloudflare.com/analytics/graphql-api/sampling/).
Live introspection confirmed `AccountAiInferenceAdaptiveGroupsSum.totalNeurons`.
The authenticated OAuth scope catalog confirmed Account Analytics Read is
`account-analytics.read`; Workers AI scopes alone returned `authz` for this dataset.
See credits.md for the exact query and limits of the estimate.

The installed Safari 27.0 server's `tools/list` and actual page reads were inspected.
`get_page_content` emits native `link/input/button uid=N` textTree records. A `savePath`
request saves a JSON extraction but returns a plain-text acknowledgment. On this
build `evaluate_javascript` did not expand its advertised `$uid(N)` macro; the adapter
avoids that macro. A real local fixture read/type/click test passed.

Cloudflare credentials were absent at the initial release. The later OAuth update
verified real linking, refresh and live Clef-flash inference on the development Mac.
The dashboard's scope details showed Workers AI Read (`ai.read`), Workers AI Write
(`ai.write`) and `offline_access`. See docs/VALIDATION.md for the actual tests.
