import hashlib
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest


def config():
    from clef_browser.oauth import OAuthConfig

    return OAuthConfig("public-client", "a" * 32, ("example.read", "example.write"))


def test_authorization_uses_fresh_pkce_without_a_secret():
    import base64

    from clef_browser.oauth import authorization

    first, state, verifier = authorization(config())
    second, next_state, next_verifier = authorization(config())
    query = parse_qs(urlsplit(first).query)
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert first != second and state != next_state and verifier != next_verifier
    assert urlsplit(first).netloc == "dash.cloudflare.com"
    assert query["redirect_uri"] == ["http://127.0.0.1:8766/oauth/callback"]
    assert query["code_challenge"] == [expected.decode()]
    assert query["code_challenge_method"] == ["S256"]
    assert set(query["scope"][0].split()) == {"example.read", "example.write", "offline_access"}
    assert "client_secret" not in query and verifier not in first


@pytest.mark.parametrize(
    "url",
    [
        "/oauth/callback?code=stolen&state=wrong",
        "/oauth/callback?code=a&code=b&state=expected",
        "/elsewhere?code=a&state=expected",
        "/oauth/callback?error=access_denied&state=wrong",
        "/oauth/callback?code=a&state=%E2%98%83",
    ],
)
def test_callback_rejects_invalid_or_ambiguous_responses(url):
    from clef_browser.oauth import callback_code

    assert callback_code(url, "expected") is None


def test_callback_accepts_matching_state_and_redacts_denial():
    from clef_browser.oauth import OAuthError, callback_code

    assert (
        callback_code("/oauth/callback?code=authorized&state=expected", "expected") == "authorized"
    )
    with pytest.raises(OAuthError, match="denied") as error:
        callback_code(
            "/oauth/callback?error=access_denied&error_description=secret&state=expected",
            "expected",
        )
    assert "secret" not in str(error.value)


async def test_exchange_and_refresh_use_form_encoding_and_rotate_tokens():
    from clef_browser.oauth import OAuthClient

    def response(request):
        form = parse_qs(request.content.decode())
        assert request.url == "https://dash.cloudflare.com/oauth2/token"
        assert "client_secret" not in form
        assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
        if form["grant_type"] == ["authorization_code"]:
            assert form["code_verifier"] == ["verifier"]
            return httpx.Response(
                200,
                json={
                    "access_token": "access-one",
                    "refresh_token": "refresh-one",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        assert form["refresh_token"] == ["refresh-one"]
        return httpx.Response(
            200,
            json={
                "access_token": "access-two",
                "refresh_token": "refresh-two",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        client = OAuthClient(http)
        record = await client.exchange(config(), "code", "verifier")
        fresh = await client.refresh(record)
    assert fresh.access_token == "access-two" and fresh.refresh_token == "refresh-two"
    assert "access-two" not in repr(fresh) and "refresh-two" not in repr(fresh)


@pytest.mark.parametrize(
    "body",
    [
        {"access_token": "sensitive", "token_type": "Bearer", "expires_in": 3600},
        {
            "access_token": "sensitive",
            "refresh_token": "private",
            "token_type": "Bearer",
            "expires_in": -1,
        },
        {
            "access_token": "sensitive",
            "refresh_token": "private",
            "token_type": "Other",
            "expires_in": 3600,
        },
        {
            "access_token": "sensitive",
            "refresh_token": "private",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "example.read",
        },
    ],
)
async def test_malformed_or_insufficient_grants_never_become_a_connection(body):
    from clef_browser.oauth import OAuthClient, OAuthError

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        with pytest.raises(OAuthError) as error:
            await OAuthClient(http).exchange(config(), "code", "verifier")
    assert "sensitive" not in str(error.value) and "private" not in str(error.value)


async def test_expired_connection_is_refreshed_and_persisted_before_api_use(tmp_path):
    from clef_browser.auth import OAuthAuth
    from clef_browser.oauth import OAuthClient, OAuthRecord

    class Store:
        record = OAuthRecord(config(), "old-access", "old-refresh", time.time() - 1)

        def load(self):
            return self.record

        def save(self, record):
            self.record = record

    store = Store()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        )
    ) as http:
        auth = OAuthAuth(tmp_path, store, OAuthClient(http))
        assert await auth.token() == "new-access"
        assert store.record.refresh_token == "new-refresh"
        assert await auth.token() == "new-access"


def test_large_keychain_record_roundtrips_without_token_files(tmp_path, monkeypatch):
    from clef_browser.auth_store import KeychainStore
    from clef_browser.oauth import OAuthRecord

    class Keychain:
        item = None

        def set(self, service, data):
            self.item = data

        def get(self, service):
            return self.item

    keychain = Keychain()
    monkeypatch.setattr("clef_browser.auth_store.NativeKeychain", lambda: keychain)
    store = KeychainStore(tmp_path)
    record = OAuthRecord(config(), "access" * 1200, "refresh" * 1200, time.time() + 3600)
    store.save(record)
    assert store.load() == record
    assert len(keychain.item) > 16000
    assert record.access_token not in (tmp_path / "connection.json").read_text()
    assert record.refresh_token not in (tmp_path / "connection.json").read_text()
    assert (tmp_path / "connection.json").stat().st_mode & 0o777 == 0o600


async def test_loopback_listener_ignores_forgery_then_accepts_real_callback():
    from clef_browser.oauth import CallbackListener

    async with CallbackListener("expected", port=0) as listener:
        async with httpx.AsyncClient(trust_env=False) as http:
            bad = await http.get(
                f"http://127.0.0.1:{listener.port}/oauth/callback?code=stolen&state=wrong"
            )
            assert bad.status_code == 400
            good = await http.get(
                f"http://127.0.0.1:{listener.port}/oauth/callback?code=good&state=expected"
            )
            assert good.status_code == 200
            assert await listener.wait(1) == "good"
            assert "good" not in good.text
