import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.main import Settings, create_app
from app.oauth import SCOPE


@pytest.mark.parametrize("auth_method", ["none", "client_secret_basic"])
def test_oauth_pkce_consent_replay_refresh_and_role_separation(tmp_path, auth_method):
    settings = Settings(
        database_path=str(tmp_path / "actions.db"),
        mcp_token="m" * 32,
        reviewer_token="r" * 32,
        oauth_issuer_url="https://gateway.test",
        oauth_database_path=str(tmp_path / "oauth.db"),
        mcp_allowed_hosts=["testserver"],
    )
    app = create_app(settings)
    with TestClient(app) as client:
        unauth = client.post("/mcp", json={})
        assert unauth.status_code == 401
        assert "/.well-known/oauth-protected-resource/mcp" in unauth.headers["www-authenticate"]
        metadata = client.get("/.well-known/oauth-authorization-server").json()
        assert metadata["code_challenge_methods_supported"] == ["S256"]
        assert (
            client.get("/.well-known/oauth-protected-resource/mcp").json()["resource"]
            == "https://gateway.test/mcp"
        )
        bad = client.post("/register", json={"redirect_uris": ["https://untrusted.test/callback"]})
        assert bad.status_code == 400
        callback = "https://api-dev.saas.aifindr.ai/callback"
        registration = client.post(
            "/register",
            json={
                "redirect_uris": [callback],
                "token_endpoint_auth_method": auth_method,
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": SCOPE,
            },
        )
        assert registration.status_code == 201, registration.text
        cid = registration.json()["client_id"]

        def token_post(path, data):
            if auth_method == "client_secret_basic":
                data = {key: value for key, value in data.items() if key != "client_id"}
                return client.post(path, data=data, auth=(cid, registration.json()["client_secret"]))
            return client.post(path, data=data)

        verifier = "v" * 64
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        params = {
            "client_id": cid,
            "redirect_uri": callback,
            "response_type": "code",
            "scope": SCOPE,
            "state": "state-fixture",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": "https://gateway.test/mcp",
        }
        invalid = client.get(
            "/authorize", params={**params, "resource": "https://untrusted.test/mcp"}, follow_redirects=False
        )
        assert "invalid_target" in invalid.headers.get("location", invalid.text)
        auth = client.get("/authorize", params=params, follow_redirects=False)
        assert auth.status_code in (302, 303, 307)
        request_id = parse_qs(urlsplit(auth.headers["location"]).query)["request"][0]
        consent_path = "/consent?request=" + request_id
        assert client.get(consent_path).status_code == 200
        assert client.post("/consent", data={"request": request_id, "approve": "true"}).status_code in (
            401,
            405,
        )
        app.state.oauth.approve(request_id)
        redirect = client.get(consent_path, follow_redirects=False)
        assert redirect.status_code == 302
        args = parse_qs(urlsplit(redirect.headers["location"]).query)
        assert args["state"] == ["state-fixture"]
        form = {
            "grant_type": "authorization_code",
            "client_id": cid,
            "code": args["code"][0],
            "redirect_uri": callback,
            "code_verifier": verifier,
            "resource": "https://gateway.test/mcp",
        }
        assert token_post("/token", data={**form, "code_verifier": "bad"}).status_code == 400
        if auth_method == "client_secret_basic":
            no_id = {key: value for key, value in form.items() if key != "client_id"}
            assert client.post("/token", data=no_id, auth=(cid, "wrong")).status_code == 401
            assert (
                client.post(
                    "/token",
                    data={**form, "client_id": "other"},
                    auth=(cid, registration.json()["client_secret"]),
                ).status_code
                == 401
            )
        assert token_post("/token", data={**form, "resource": "https://other.test/mcp"}).status_code == 400
        issued = token_post("/token", data=form)
        assert issued.status_code == 200, issued.text
        tokens = issued.json()
        assert token_post("/token", data=form).status_code == 400
        headers = {
            "Authorization": "Bearer " + tokens["access_token"],
            "Accept": "application/json, text/event-stream",
        }
        assert client.get("/actions", headers=headers).status_code == 401
        assert client.get("/mcp", headers=headers).status_code == 405
        assert client.get("/mcp", headers={**headers, "Origin": "https://untrusted.test"}).status_code == 403
        initialized = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "oauth-test", "version": "1"},
                },
            },
        )
        assert initialized.status_code == 200
        refresh = {"grant_type": "refresh_token", "client_id": cid, "refresh_token": tokens["refresh_token"]}
        rotated = token_post("/token", data=refresh)
        assert rotated.status_code == 200, rotated.text
        assert token_post("/token", data=refresh).status_code == 400
        assert client.post("/mcp", headers=headers, json={}).status_code == 401
        revoke = token_post("/revoke", data={"client_id": cid, "token": rotated.json()["access_token"]})
        assert revoke.status_code == 200
        assert (
            token_post(
                "/token", data={**refresh, "refresh_token": rotated.json()["refresh_token"]}
            ).status_code
            == 400
        )
        # Access and refresh values are never persisted in plaintext.
        assert tokens["access_token"].encode() not in (tmp_path / "oauth.db").read_bytes()
        assert tokens["refresh_token"].encode() not in (tmp_path / "oauth.db").read_bytes()
