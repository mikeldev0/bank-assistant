"""Authentication and refresh-token regressions against the actual MCP SDK."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from mcp.server.auth.provider import TokenError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import ValidationError

from app.main import Settings, create_app
from app.oauth import SCOPE, OAuthProvider


def client_info(client_id="audit-client"):
    return OAuthClientInformationFull(
        client_id=client_id,
        redirect_uris=["https://api-dev.saas.aifindr.ai/callback"],
        token_endpoint_auth_method="none",
    )


def issue(provider, client):
    with provider.db() as db:
        return provider.issue(db, client.client_id, [SCOPE])


def test_malformed_and_duplicate_bearer_headers_fail_closed(tmp_path):
    app = create_app(Settings(
        database_path=str(tmp_path / "actions.db"), mcp_token="m" * 32,
        reviewer_token="r" * 32, mcp_allowed_hosts=["testserver"],
    ))
    with TestClient(app) as client:
        for path, token in [("/actions", b"r" * 32), ("/mcp", b"m" * 32)]:
            for headers in [
                [(b"authorization", b"Bearer " + b"\xe9" * 32)],
                [(b"authorization", b"Bearer " + token), (b"authorization", b"Bearer bad")],
                [(b"authorization", b"Bearer bad"), (b"authorization", b"Bearer " + token)],
            ]:
                assert client.get(path, headers=headers).status_code == 401
        assert client.get("/actions", headers={"Authorization": "bearer " + "r" * 32}).status_code == 200


@pytest.mark.parametrize("token", ["\u00e9" * 32, "x " * 32, "x" * 257, "x" * 31])
def test_config_rejects_non_bearer_credentials(token):
    with pytest.raises(ValidationError):
        Settings(mcp_token=token, reviewer_token="r" * 32)


@pytest.mark.parametrize("port", ["bad", "65536"])
def test_config_rejects_malformed_review_port(port):
    with pytest.raises(ValidationError):
        Settings(mcp_token="m" * 32, reviewer_token="r" * 32, review_base_url=f"https://review.test:{port}")


@pytest.mark.parametrize("replay_path", ["load", "exchange"])
def test_refresh_replay_revokes_successor_even_with_preloaded_token(tmp_path, replay_path):
    provider = OAuthProvider(str(tmp_path / "oauth.db"), "https://gateway.test")
    client = client_info()
    original = issue(provider, client)
    loaded = asyncio.run(provider.load_refresh_token(client, original.refresh_token))
    rotated = asyncio.run(provider.exchange_refresh_token(client, loaded, [SCOPE]))
    assert asyncio.run(provider.load_access_token(rotated.access_token)) is not None
    if replay_path == "load":
        assert asyncio.run(provider.load_refresh_token(client, original.refresh_token)) is None
    else:
        with pytest.raises(TokenError):
            asyncio.run(provider.exchange_refresh_token(client, loaded, [SCOPE]))
    assert asyncio.run(provider.load_access_token(rotated.access_token)) is None
    assert asyncio.run(provider.load_refresh_token(client, rotated.refresh_token)) is None


def test_wrong_client_cannot_revoke_another_family(tmp_path):
    provider = OAuthProvider(str(tmp_path / "oauth.db"), "https://gateway.test")
    client = client_info()
    original = issue(provider, client)
    loaded = asyncio.run(provider.load_refresh_token(client, original.refresh_token))
    rotated = asyncio.run(provider.exchange_refresh_token(client, loaded, [SCOPE]))
    assert asyncio.run(provider.load_refresh_token(client_info("other"), original.refresh_token)) is None
    assert asyncio.run(provider.load_access_token(rotated.access_token)) is not None


@pytest.mark.parametrize("change", ["issuer", "subject"])
def test_refresh_grants_cannot_cross_resource_or_owner(tmp_path, change):
    path = str(tmp_path / "oauth.db")
    provider = OAuthProvider(path, "https://gateway.test", "owner-a")
    client = client_info()
    tokens = issue(provider, client)
    loaded = asyncio.run(provider.load_refresh_token(client, tokens.refresh_token))
    other = OAuthProvider(
        path, "https://other.test" if change == "issuer" else "https://gateway.test",
        "owner-b" if change == "subject" else "owner-a",
    )
    assert asyncio.run(other.load_access_token(tokens.access_token)) is None
    assert asyncio.run(other.load_refresh_token(client, tokens.refresh_token)) is None
    with pytest.raises(TokenError):
        asyncio.run(other.exchange_refresh_token(client, loaded, [SCOPE]))
    assert asyncio.run(provider.load_access_token(tokens.access_token)) is not None


def test_refresh_rotation_does_not_extend_family_lifetime(tmp_path, monkeypatch):
    now = 1_800_000_000
    monkeypatch.setattr("app.oauth.time.time", lambda: now)
    provider = OAuthProvider(str(tmp_path / "oauth.db"), "https://gateway.test")
    client = client_info()
    tokens = issue(provider, client)
    loaded = asyncio.run(provider.load_refresh_token(client, tokens.refresh_token))
    deadline = loaded.expires_at
    now += 3600
    rotated = asyncio.run(provider.exchange_refresh_token(client, loaded, [SCOPE]))
    assert asyncio.run(provider.load_refresh_token(client, rotated.refresh_token)).expires_at == deadline
    now = deadline
    assert asyncio.run(provider.load_access_token(rotated.access_token)) is None
    assert asyncio.run(provider.load_refresh_token(client, rotated.refresh_token)) is None
