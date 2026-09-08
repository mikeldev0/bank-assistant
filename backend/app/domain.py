"""Deterministic transfer policy. No bank connections or real monetary effects."""

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    recipient: str = Field(min_length=2, max_length=80, pattern=r"^[\w .'-]+$")
    destination: str = Field(pattern=r"^DEMO-[A-Z0-9]{4,12}$")
    amount_cents: int = Field(strict=True, gt=0, le=100000)
    concept: str = Field(min_length=1, max_length=140)
    idempotency_key: str = Field(min_length=8, max_length=100)


class DomainError(Exception):
    def __init__(self, message: str, status: int = 409):
        self.message, self.status = message, status


class Store:
    def __init__(self, path: str, ttl: int = 600):
        if type(ttl) is not int or not 1 <= ttl <= 3600:
            raise ValueError("TTL must be an integer between 1 and 3600 seconds")
        self.path, self.ttl = path, ttl
        descriptor = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(descriptor)
        os.chmod(path, 0o600)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                    status TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    UNIQUE(owner, key));
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT NOT NULL,
                    event TEXT NOT NULL, actor TEXT NOT NULL, at REAL NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def event(db, action_id, event, actor):
        db.execute(
            "INSERT INTO audit(action_id,event,actor,at) VALUES(?,?,?,?)",
            (action_id, event, actor, time.time()),
        )

    @staticmethod
    def serialize(row):
        return {
            "id": row["id"],
            **json.loads(row["payload"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "fingerprint": row["fingerprint"],
            "currency": "EUR",
            "simulated": True,
        }

    def expire(self, db, owner, now=None):
        rows = db.execute(
            "SELECT id FROM actions WHERE owner=? AND status='pending' AND expires_at<=?",
            (owner, time.time() if now is None else now),
        ).fetchall()
        for row in rows:
            db.execute("UPDATE actions SET status='expired' WHERE id=?", (row["id"],))
            self.event(db, row["id"], "expired", "system")

    def propose(self, owner: str, proposal: Proposal):
        payload = proposal.model_dump(exclude={"idempotency_key"})
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.expire(db, owner)
            existing = db.execute(
                "SELECT * FROM actions WHERE owner=? AND key=?", (owner, proposal.idempotency_key)
            ).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise DomainError("La clave de idempotencia ya corresponde a otros datos.")
                return self.serialize(existing)
            action_id, now = str(uuid4()), time.time()
            db.execute(
                "INSERT INTO actions VALUES(?,?,?,?,?,?,?,?)",
                (
                    action_id,
                    owner,
                    proposal.idempotency_key,
                    fingerprint,
                    encoded,
                    "pending",
                    now,
                    now + self.ttl,
                ),
            )
            self.event(db, action_id, "proposed", "agent")
            return self.serialize(db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone())

    def list(self, owner: str):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.expire(db, owner)
            return [
                self.serialize(r)
                for r in db.execute(
                    "SELECT * FROM actions WHERE owner=? ORDER BY created_at DESC LIMIT 100", (owner,)
                )
            ]

    def get(self, owner: str, action_id: str):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.expire(db, owner)
            row = db.execute("SELECT * FROM actions WHERE id=? AND owner=?", (action_id, owner)).fetchone()
            if row is None:
                raise DomainError("Acción no encontrada.", 404)
            result = self.serialize(row)
            result["audit"] = [
                dict(r)
                for r in db.execute(
                    "SELECT event,actor,at FROM audit WHERE action_id=? ORDER BY seq", (action_id,)
                )
            ]
            return result

    def decide(self, owner: str, action_id: str, fingerprint: str, confirm: bool):
        if type(confirm) is not bool:
            raise DomainError("Decision must be an explicit boolean.", 422)
        error = None
        result = None
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # One authorization-state snapshot, taken AFTER acquiring the writer
            # lock. Expiration and decision cannot race between transactions.
            now = time.time()
            self.expire(db, owner, now)
            row = db.execute("SELECT * FROM actions WHERE id=? AND owner=?", (action_id, owner)).fetchone()
            target = "executed" if confirm else "rejected"
            if row is None:
                error = DomainError("Acci\u00f3n no encontrada.", 404)
            elif row["fingerprint"] != fingerprint:
                error = DomainError("Los datos revisados no coinciden con la propuesta.")
            elif row["status"] == target:
                result = self.serialize(row)
            elif row["status"] != "pending":
                error = DomainError("La acci\u00f3n ya no admite confirmaci\u00f3n.")
            else:
                if confirm:
                    self.event(db, action_id, "confirmed", "human")
                # Simulation and state change share one transaction: no external side effect.
                db.execute("UPDATE actions SET status=? WHERE id=?", (target, action_id))
                self.event(db, action_id, target, "simulator" if confirm else "human")
                result = self.serialize(
                    db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
                )
        # Raise only after the transaction commits, retaining an expiration event
        # even when a stale or altered confirmation is refused.
        if error:
            raise error
        return result
