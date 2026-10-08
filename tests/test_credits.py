import json
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest

ACCOUNT = "a" * 32
NOW = datetime(2026, 10, 8, 0, 3, tzinfo=UTC)


async def token():
    return "test-only-bearer"


def response(groups, account=ACCOUNT):
    return {
        "data": {
            "viewer": {"accounts": [{"accountTag": account, "aiInferenceAdaptiveGroups": groups}]}
        },
        "errors": None,
    }


async def test_reads_whole_account_utc_day_without_model_or_source_filters():
    from clef_browser.credits import CreditsClient

    def handler(request):
        assert str(request.url) == "https://api.cloudflare.com/client/v4/graphql"
        assert request.headers["Authorization"] == "Bearer test-only-bearer"
        body = json.loads(request.content)
        # The live schema requires a non-null filter; reject an invalid query.
        if "$filter: AccountAiInferenceAdaptiveGroupsFilter_InputObject!" not in body["query"]:
            return httpx.Response(
                200,
                json={
                    "data": None,
                    "errors": [{"message": "filter must be non-null"}],
                },
            )
        assert body["variables"] == {
            "accountTag": ACCOUNT,
            "filter": {
                "datetime_geq": "2026-10-08T00:00:00Z",
                "datetime_lt": "2026-10-08T00:03:00Z",
            },
        }
        # No dimensions: one aggregate covers every model and request source.
        assert "dimensions" not in body["query"]
        return httpx.Response(200, json=response([{"count": 17, "sum": {"totalNeurons": 725.25}}]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        local_time = NOW.astimezone(timezone(timedelta(hours=-7)))
        result = await CreditsClient(ACCOUNT, token, http, clock=lambda: local_time).usage()
    assert result["used_neurons"] == 725.25
    assert result["remaining_free_neurons_estimate"] == 9274.75
    assert result["free_allowance_neurons"] == 10000
    assert result["used_percent"] == 7.2525
    assert result["requests"] == 17
    assert result["utc_day"] == "2026-10-08"
    assert result["resets_at"] == "2026-10-09T00:00:00Z"
    assert result["query_end"] == "2026-10-08T00:03:00Z"
    assert result["is_estimate"] is True
    assert "delay" in result["note"]


@pytest.mark.parametrize("neurons,remaining,over", [(10000, 0, 0), (12000.5, 0, 2000.5)])
async def test_exhausted_allocation_never_reports_negative_remaining(neurons, remaining, over):
    from clef_browser.credits import CreditsClient

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json=response([{"count": 100, "sum": {"totalNeurons": neurons}}])
            )
        )
    ) as http:
        result = await CreditsClient(ACCOUNT, token, http, clock=lambda: NOW).usage()
    assert result["remaining_free_neurons_estimate"] == remaining
    assert result["above_free_allowance_neurons"] == over
    assert result["used_percent"] >= 100


async def test_no_reported_events_is_distinguished_from_missing_data():
    from clef_browser.credits import CreditsClient

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response([])))
    ) as http:
        result = await CreditsClient(ACCOUNT, token, http, clock=lambda: NOW).usage()
    assert result["used_neurons"] == 0
    assert result["data_status"] == "no_reported_events"
    assert result["is_estimate"] is True


@pytest.mark.parametrize(
    "data",
    [
        {"data": None},
        {"data": {"viewer": {"accounts": []}}},
        response([{"count": 1, "sum": {"totalNeurons": 2}}], "b" * 32),
        response(None),
        response([{"count": 1, "sum": {}}]),
        response([{"count": 1, "sum": {"totalNeurons": None}}]),
        response([{"count": 1, "sum": {"totalNeurons": -2}}]),
        response([{"count": 1, "sum": {"totalNeurons": True}}]),
        response([{"count": 1, "sum": {"totalNeurons": "0"}}]),
        response([{"count": -1, "sum": {"totalNeurons": 0}}]),
        response([{"count": 1, "sum": {"totalNeurons": 2}}] * 2),
    ],
)
async def test_invalid_analytics_never_turns_into_a_full_free_balance(data):
    from clef_browser.credits import CreditsClient, CreditsError

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    ) as http:
        with pytest.raises(CreditsError):
            await CreditsClient(ACCOUNT, token, http, clock=lambda: NOW).usage()


async def test_graphql_permission_failure_is_actionable_and_does_not_expose_server_text():
    from clef_browser.credits import CreditsClient, CreditsError

    data = {
        **response([{"count": 1, "sum": {"totalNeurons": 0}}]),
        "errors": [
            {"message": "server included test-only-bearer", "extensions": {"code": "authz"}}
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    ) as http:
        with pytest.raises(CreditsError) as error:
            await CreditsClient(ACCOUNT, token, http, clock=lambda: NOW).usage()
    assert "account-analytics.read" in str(error.value)
    assert "test-only-bearer" not in str(error.value)


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_http_errors_are_safe_and_not_inference_requests(status):
    from clef_browser.credits import CreditsClient, CreditsError

    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(status, text="test-only-bearer")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(CreditsError) as error:
            await CreditsClient(ACCOUNT, token, http, clock=lambda: NOW).usage()
    assert "test-only-bearer" not in str(error.value)
    assert calls == ["/client/v4/graphql"]


async def test_timeout_is_safe_and_does_not_claim_zero_usage():
    from clef_browser.credits import CreditsClient, CreditsError

    def handler(request):
        raise httpx.ReadTimeout("test-only-bearer", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(CreditsError) as error:
            await CreditsClient(ACCOUNT, token, http, clock=lambda: NOW).usage()
    assert "test-only-bearer" not in str(error.value)


async def test_cli_and_mcp_read_credits_without_debiting_local_budget(
    tmp_path, monkeypatch, capsys
):
    from clef_browser.budget import Budget
    from clef_browser.cli import main
    from clef_browser.config import Settings
    from clef_browser.server import create_server

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLEF_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT)
    monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-only-bearer")
    # Replace only the external HTTP boundary; real auth, report, CLI and tools run.
    original = httpx.AsyncClient

    def handler(request):
        assert request.url.path == "/client/v4/graphql"
        return httpx.Response(200, json=response([{"count": 8, "sum": {"totalNeurons": 400}}]))

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(handler))
    )
    budget = Budget(tmp_path / "usage.sqlite3")
    budget.reserve("clef-flash", {"state": "existing task"})
    before = budget.usage()
    # CLI owns its event loop; run it in a worker from this async test.
    import asyncio

    assert await asyncio.to_thread(main, ["credits"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ready"
    assert report["cloudflare"]["remaining_free_neurons_estimate"] == 9600
    assert report["local_budget"] == before
    server = create_server(
        Settings(account_id=ACCOUNT, token="test-only-bearer", state_dir=tmp_path)
    )
    result = await server.call_tool("account_usage", {})
    content = result[0] if isinstance(result, tuple) else result
    mcp_report = json.loads(content[0].text)
    assert mcp_report["cloudflare"]["used_neurons"] == 400
    assert budget.usage() == before


def test_unlinked_credit_check_preserves_local_ledger_and_reports_unknown(
    tmp_path, monkeypatch, capsys
):
    from clef_browser.cli import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLEF_STATE_DIR", str(tmp_path))
    for name in ("CLOUDFLARE_AUTH_TOKEN", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)
    assert main(["credits"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "unavailable"
    assert report["cloudflare"] is None
    assert report["local_budget"]["reserved_neurons"] == 0
