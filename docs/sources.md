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
- [WebKit's Safari MCP announcement](https://webkit.org/blog/18136/introducing-the-safari-mcp-server-for-web-developers/):
  native server, prerequisites, tools and personal-data limitations.
- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk):
  stdio client, ClientSession and FastMCP.

## Direct native observations

The installed Safari 27.0 server's `tools/list` and actual page reads were inspected.
`get_page_content` emits native `link/input/button uid=N` textTree records. A `savePath`
request saves a JSON extraction but returns a plain-text acknowledgment. On this
build `evaluate_javascript` did not expand its advertised `$uid(N)` macro; the adapter
avoids that macro. A real local fixture read/type/click test passed.

Cloudflare credentials were absent on the development Mac. The initial API tests
use the documented schemas and a controlled HTTP transport. Live inference remains
an explicit user setup check, not a claimed test result.
