"""Deterministic domain and local-secret regression tests; no network required."""

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from app.domain import DomainError, Proposal, Store
from scripts.setup_local import create_configuration


def make_proposal(**changes):
    return Proposal(
        **(
            {
                "recipient": "Audit Demo",
                "destination": "DEMO-1234",
                "amount_cents": 2500,
                "concept": "Regression",
                "idempotency_key": "audit-key-1234",
            }
            | changes
        )
    )


def test_action_database_is_private(tmp_path):
    path = tmp_path / "actions.db"
    path.touch(mode=0o644)
    Store(str(path))
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("ttl", [True, 0, -1, 3601, 1.5])
def test_invalid_ttl_rejected(tmp_path, ttl):
    with pytest.raises(ValueError):
        Store(str(tmp_path / "actions.db"), ttl)


def test_expired_decision_commits_status_and_audit_before_error(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "actions.db"))
    action = store.propose("alice", make_proposal())
    monkeypatch.setattr("app.domain.time.time", lambda: action["expires_at"])
    with pytest.raises(DomainError):
        store.decide("alice", action["id"], action["fingerprint"], True)
    # Inspect the DB directly: a subsequent Store.get must not be what expires it.
    with store.connection() as db:
        assert db.execute("SELECT status FROM actions").fetchone()[0] == "expired"
        assert [row[0] for row in db.execute("SELECT event FROM audit ORDER BY seq")] == [
            "proposed",
            "expired",
        ]


def test_decision_uses_one_transaction_and_retries_are_safe(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "actions.db"))
    action = store.propose("alice", make_proposal())
    original = store.connection
    calls = []

    @contextmanager
    def counted():
        calls.append(1)
        with original() as db:
            yield db

    monkeypatch.setattr(store, "connection", counted)
    assert store.decide("alice", action["id"], action["fingerprint"], True)["status"] == "executed"
    assert len(calls) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: store.decide("alice", action["id"], action["fingerprint"], True), range(32)))
    assert [event["event"] for event in store.get("alice", action["id"])["audit"]] == [
        "proposed",
        "confirmed",
        "executed",
    ]


def test_decision_rejects_truthy_non_boolean_input(tmp_path):
    store = Store(str(tmp_path / "actions.db"))
    action = store.propose("alice", make_proposal())
    with pytest.raises(DomainError):
        store.decide("alice", action["id"], action["fingerprint"], "false")
    assert store.get("alice", action["id"])["status"] == "pending"


def configuration_root(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    return tmp_path


def test_setup_secrets_private_separate_and_preserved(tmp_path):
    root = configuration_root(tmp_path)
    create_configuration(root)
    paths = [root / "backend/.env", root / "frontend/.env.local"]
    originals = [path.read_bytes() for path in paths]
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in paths)
    back, front = [
        dict(line.split("=", 1) for line in content.decode().splitlines()) for content in originals
    ]
    assert back["REVIEWER_TOKEN"] == front["REVIEWER_TOKEN"]
    assert (
        len({back["REVIEWER_TOKEN"], back["MCP_TOKEN"], front["REVIEW_PASSWORD"], front["SESSION_SECRET"]})
        == 4
    )
    with pytest.raises(FileExistsError):
        create_configuration(root)
    assert [path.read_bytes() for path in paths] == originals


def test_setup_rollback_does_not_overwrite_a_competing_file(tmp_path):
    root = configuration_root(tmp_path)
    original = os.open
    frontend = root / "frontend/.env.local"

    def competing_open(path, flags, mode=0o777):
        if Path(path) == frontend:
            frontend.write_text("EXISTING=keep\n")
        return original(path, flags, mode)

    with patch("scripts.setup_local.os.open", side_effect=competing_open):
        with pytest.raises(FileExistsError):
            create_configuration(root)
    assert not (root / "backend/.env").exists()
    assert frontend.read_text() == "EXISTING=keep\n"
