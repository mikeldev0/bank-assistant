from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain import DomainError, Proposal, Store
from app.main import Settings, create_app


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "test.db"))


def proposal(**overrides):
    return Proposal(
        **(
            {
                "recipient": "Alex Demo",
                "destination": "DEMO-1234",
                "amount_cents": 12500,
                "concept": "Cena",
                "idempotency_key": "test-key-0001",
            }
            | overrides
        )
    )


def test_happy_path_and_audit(store):
    a = store.propose("alice", proposal())
    assert a["status"] == "pending"
    result = store.decide("alice", a["id"], a["fingerprint"], True)
    assert result["status"] == "executed" and result["simulated"]
    assert [e["event"] for e in store.get("alice", a["id"])["audit"]] == ["proposed", "confirmed", "executed"]


def test_concurrent_retries_exactly_one_simulation(store):
    with ThreadPoolExecutor(max_workers=8) as pool:
        actions = list(pool.map(lambda _: store.propose("alice", proposal()), range(16)))
    assert len({a["id"] for a in actions}) == 1
    a = actions[0]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: store.decide("alice", a["id"], a["fingerprint"], True), range(16)))
    assert len(store.get("alice", a["id"])["audit"]) == 3


def test_conflicting_idempotency_payload(store):
    store.propose("alice", proposal())
    with pytest.raises(DomainError):
        store.propose("alice", proposal(amount_cents=999))


def test_cross_user_access(store):
    a = store.propose("alice", proposal())
    with pytest.raises(DomainError) as exc:
        store.get("mallory", a["id"])
    assert exc.value.status == 404
    with pytest.raises(DomainError):
        store.decide("mallory", a["id"], a["fingerprint"], True)
    assert store.list("mallory") == []


def test_expiration(store):
    a = store.propose("alice", proposal())
    with store.connection() as db:
        db.execute("UPDATE actions SET expires_at=0 WHERE id=?", (a["id"],))
    with pytest.raises(DomainError):
        store.decide("alice", a["id"], a["fingerprint"], True)
    assert store.get("alice", a["id"])["status"] == "expired"
    assert len(store.get("alice", a["id"])["audit"]) == 2


def test_changed_review_and_terminal_state(store):
    a = store.propose("alice", proposal())
    with pytest.raises(DomainError):
        store.decide("alice", a["id"], "0" * 64, True)
    store.decide("alice", a["id"], a["fingerprint"], False)
    with pytest.raises(DomainError):
        store.decide("alice", a["id"], a["fingerprint"], True)


@pytest.mark.parametrize(
    "override",
    [
        {"amount_cents": 0},
        {"amount_cents": -1},
        {"amount_cents": 100001},
        {"amount_cents": 1.5},
        {"amount_cents": True},
        {"destination": "ES9121000418450200051332"},
        {"recipient": "<script>alert(1)</script>"},
        {"owner": "mallory"},
        {"confirmed": True},
    ],
)
def test_malicious_or_invalid_data(override):
    with pytest.raises(ValidationError):
        proposal(**override)


def test_role_separation_and_mcp_transport(tmp_path):
    settings = Settings(
        database_path=str(tmp_path / "api.db"),
        mcp_token="m" * 32,
        reviewer_token="r" * 32,
        mcp_allowed_hosts=["testserver"],
    )
    app = create_app(settings)
    mcp_headers = {
        "Authorization": "Bearer " + settings.mcp_token,
        "Accept": "application/json, text/event-stream",
    }
    with TestClient(app) as client:
        assert client.get("/actions").status_code == 401
        assert client.get("/actions", headers=mcp_headers).status_code == 401
        assert client.post("/mcp", json={}).status_code == 401

        def rpc(method, params, seq=1):
            response = client.post(
                "/mcp",
                headers=mcp_headers,
                json={"jsonrpc": "2.0", "id": seq, "method": method, "params": params},
            )
            assert response.status_code == 200, response.text
            return response.json()

        initialized = rpc(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        assert "result" in initialized
        listed = rpc("tools/list", {})
        assert {t["name"] for t in listed["result"]["tools"]} == {"propose_transfer", "get_transfer_status"}
        result = rpc("tools/call", {"name": "propose_transfer", "arguments": proposal().model_dump()})
        assert not result["result"].get("isError", False)
        reviewer = {"Authorization": "Bearer " + settings.reviewer_token}
        a = client.get("/actions", headers=reviewer).json()[0]
        body = {"fingerprint": a["fingerprint"], "decision": "confirm"}
        assert client.post(f"/actions/{a['id']}/decision", headers=mcp_headers, json=body).status_code == 401
        assert (
            client.post(f"/actions/{a['id']}/decision", headers=reviewer, json=body).json()["status"]
            == "executed"
        )
        status = rpc("tools/call", {"name": "get_transfer_status", "arguments": {"action_id": a["id"]}})
        assert "executed" in str(status)


def test_credentials_must_be_separate():
    with pytest.raises(ValidationError):
        Settings(mcp_token="x" * 32, reviewer_token="x" * 32)
