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
