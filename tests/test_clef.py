import json

import httpx
import pytest


def payload():
    return {
        "state": {"goal": "Open docs", "page": "Docs link"},
        "questions": {
            "next_action": {
                "type": "choice",
                "instructions": "Choose the next action",
                "criteria": {"click_7": "Open docs", "stop": "Stop"},
            },
            "goal_complete": {"type": "noul", "instructions": "Is the goal complete?"},
        },
    }


def response(choice="click_7", probabilities=None, complete=0.1):
    return {
        "success": True,
        "result": {
            "model": "clef-flash",
            "answers": {
                "next_action": {
                    "type": "choice",
                    "choice": choice,
                    "confidence": 0.9,
                    "probabilities": probabilities or {"click_7": 0.95, "stop": 0.05},
                },
                "goal_complete": {"type": "noul", "noul": complete},
            },
            "usage": {"input_tokens": 300, "output_tokens": 0},
        },
    }


async def test_exact_clef_api_contract_and_decision(tmp_path):
    from clef_browser.budget import Budget
    from clef_browser.clef import ClefClient

    budget = Budget(tmp_path / "usage.sqlite")

    def transport(request):
        assert str(request.url).endswith("/ai/run/@cf/cloudflare/clef-flash")
        assert request.headers["Authorization"] == "Bearer test-token"
        body = json.loads(request.content)
        assert body["model"] == "clef-flash"
        assert "messages" not in body
        assert body["questions"]["next_action"]["criteria"] == {
            "click_7": "Open docs",
            "stop": "Stop",
        }
        assert budget.usage()["requests"] == 1
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        client = ClefClient("a" * 32, "test-token", budget, http=http)
        decision = await client.decide(payload())
    assert decision.choice == "click_7"
    assert decision.probability == 0.95
    assert decision.complete == 0.1
    assert budget.usage()["input_tokens"] == 300


@pytest.mark.parametrize(
    "bad",
    [
        response("invented"),
        response(probabilities={"click_7": float("nan"), "stop": 0.1}),
        response(probabilities={"click_7": 0.2, "stop": 0.2}),
        response(probabilities={"click_7": 0.2, "stop": 0.8}),
        response(complete=2),
    ],
)
async def test_malformed_or_unoffered_choices_fail_closed(tmp_path, bad):
    from clef_browser.budget import Budget
    from clef_browser.clef import ClefClient, ClefError

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=json.dumps(bad)))
    ) as http:
        with pytest.raises(ClefError):
            await ClefClient("a" * 32, "test", Budget(tmp_path / "b.sqlite"), http=http).decide(
                payload()
            )


async def test_transient_retries_are_bounded_and_each_reserves(tmp_path):
    from clef_browser.budget import Budget
    from clef_browser.clef import ClefClient, ClefError

    budget = Budget(tmp_path / "b.sqlite")

    async def no_sleep(_):
        pass

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(503, json={"errors": [{"code": 3040}]})
        )
    ) as http:
        with pytest.raises(ClefError):
            await ClefClient("a" * 32, "test", budget, http=http, sleep=no_sleep).decide(payload())
    assert budget.usage()["requests"] == 3


@pytest.mark.parametrize("status,code", [(401, 10000), (403, 5035), (429, 3036), (200, 3036)])
async def test_auth_and_daily_quota_do_not_retry(tmp_path, status, code):
    from clef_browser.budget import Budget
    from clef_browser.clef import ClefClient, ClefError

    budget = Budget(tmp_path / "b.sqlite")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                status, json={"success": False, "errors": [{"code": code, "message": "quota"}]}
            )
        )
    ) as http:
        with pytest.raises(ClefError):
            await ClefClient("a" * 32, "test", budget, http=http).decide(payload())
    assert budget.usage()["requests"] == 1


async def test_oversize_or_images_refused_before_network(tmp_path):
    from clef_browser.budget import Budget
    from clef_browser.clef import ClefClient

    budget = Budget(tmp_path / "b.sqlite")
    client = ClefClient("a" * 32, "test", budget)
    with pytest.raises(ValueError):
        await client.decide({**payload(), "state": "x" * 25000})
    with pytest.raises(ValueError):
        await client.decide({**payload(), "images": ["data:image/png;base64,aaa"]})
    assert budget.usage()["requests"] == 0


async def test_server_disconnect_is_budgeted_retried_and_reported(tmp_path):
    from clef_browser.budget import Budget
    from clef_browser.clef import ClefClient, ClefError

    budget = Budget(tmp_path / "b.sqlite")

    def disconnect(request):
        raise httpx.RemoteProtocolError("Server disconnected", request=request)

    async def no_sleep(_):
        pass

    async with httpx.AsyncClient(transport=httpx.MockTransport(disconnect)) as http:
        with pytest.raises(ClefError):
            await ClefClient("a" * 32, "test", budget, http=http, sleep=no_sleep).decide(payload())
    assert budget.usage()["requests"] == 3
