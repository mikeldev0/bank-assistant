"""Assessment OAuth provider: SDK protocol handlers, explicit local operator consent.

Single project only. Local approval is separate from transfer confirmation. Tokens
are opaque, expire, are audience-bound and are stored by hash in a private SQLite DB.
"""

import base64
import binascii
import hashlib
import html
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import unquote_plus, urlencode, urlsplit

from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.middleware.client_auth import AuthenticationError, ClientAuthenticator
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

SCOPE = "transfers:propose-read"
CALLBACK_ORIGINS = {"https://api-dev.saas.aifindr.ai", "https://hub-dev.aifindr.ai"}


class OAuthProvider:
    def __init__(self, path, issuer, subject="assessment-user"):
        self.path, self.issuer, self.subject = path, issuer.rstrip("/"), subject
        self.resource = self.issuer + "/mcp"
        parts = urlsplit(self.issuer)
        _ = parts.port
        if parts.scheme != "https" and not (
            parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost"}
        ):
            raise ValueError("OAuth issuer requires HTTPS")
        if (
            not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path
        ):
            raise ValueError("OAuth issuer must be a clean origin")
        descriptor = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(descriptor)
        os.chmod(path, 0o600)
        with self.db(cleanup=False) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS oauth (kind TEXT, key TEXT, data TEXT, expires REAL, family TEXT, PRIMARY KEY(kind,key))"
            )

    @contextmanager
    def db(self, cleanup=True):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                if cleanup:
                    db.execute("DELETE FROM oauth WHERE expires <= ?", (time.time(),))
                yield db
        finally:
            db.close()

    @staticmethod
    def hashed(key):
        return hashlib.sha256(key.encode()).hexdigest()

    def put(self, db, kind, key, data, expires, family=""):
        db.execute(
            "INSERT INTO oauth VALUES(?,?,?,?,?)", (kind, self.hashed(key), json.dumps(data), expires, family)
        )

    def get(self, db, kind, key):
        row = db.execute("SELECT * FROM oauth WHERE kind=? AND key=?", (kind, self.hashed(key))).fetchone()
        return json.loads(row["data"]) if row else None

    async def get_client(self, client_id):
        with self.db() as db:
            data = self.get(db, "client", client_id)
        return OAuthClientInformationFull.model_validate(data) if data else None

    async def register_client(self, client_info):
        for uri in client_info.redirect_uris or []:
            parts = urlsplit(str(uri))
            if (
                f"{parts.scheme}://{parts.netloc}" not in CALLBACK_ORIGINS
                or parts.fragment
                or parts.username
                or parts.password
            ):
                raise RegistrationError("invalid_redirect_uri", "Only AIFindr DEV callbacks are permitted")
        if not client_info.redirect_uris:
            raise RegistrationError("invalid_redirect_uri", "A redirect URI is required")
        with self.db() as db:
            if db.execute("SELECT COUNT(*) FROM oauth WHERE kind='client'").fetchone()[0] >= 50:
                raise RegistrationError("invalid_client_metadata", "Registration capacity reached")
            self.put(
                db,
                "client",
                client_info.client_id,
                client_info.model_dump(mode="json"),
                time.time() + 7 * 86400,
            )

    async def authorize(self, client, params):
        if params.resource not in (None, self.resource):
            raise AuthorizeError("invalid_target", "Resource must be this MCP")
        if params.scopes and set(params.scopes) != {SCOPE}:
            raise AuthorizeError("invalid_scope", "Only proposal and status access is available")
        request_id = secrets.token_urlsafe(32)
        with self.db() as db:
            if db.execute("SELECT COUNT(*) FROM oauth WHERE kind='pending'").fetchone()[0] >= 50:
                raise AuthorizeError("temporarily_unavailable", "Too many pending consent requests")
            self.put(
                db,
                "pending",
                request_id,
                {"client_id": client.client_id, "params": params.model_dump(mode="json"), "approved": False},
                time.time() + 300,
            )
        return self.issuer + "/consent?request=" + request_id

    def approve(self, request_id):
        """Only callable locally, never exposed as a tool or unauthenticated HTTP mutation."""
        with self.db() as db:
            pending = self.get(db, "pending", request_id)
            if not pending or pending["approved"]:
                raise ValueError("Consent request expired, absent or already approved")
            params = pending["params"]
            code = secrets.token_urlsafe(32)
            authorization = AuthorizationCode(
                code=code,
                client_id=pending["client_id"],
                scopes=[SCOPE],
                expires_at=time.time() + 60,
                code_challenge=params["code_challenge"],
                redirect_uri=params["redirect_uri"],
                redirect_uri_provided_explicitly=params["redirect_uri_provided_explicitly"],
                resource=self.resource,
                subject=self.subject,
            )
            self.put(
                db,
                "code",
                code,
                authorization.model_dump(mode="json", exclude={"code"}),
                authorization.expires_at,
            )
            pending.update(
                {
                    "approved": True,
                    "redirect": construct_redirect_uri(
                        params["redirect_uri"], code=code, state=params["state"]
                    ),
                }
            )
            db.execute(
                "UPDATE oauth SET data=? WHERE kind='pending' AND key=?",
                (json.dumps(pending), self.hashed(request_id)),
            )

    async def consent(self, request):
        request_id = request.query_params.get("request", "")
        headers = {
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        }
        with self.db() as db:
            pending = self.get(db, "pending", request_id)
            if not pending:
                return Response("Consent request expired or absent", status_code=400, headers=headers)
            if pending["approved"]:
                db.execute("DELETE FROM oauth WHERE kind='pending' AND key=?", (self.hashed(request_id),))
                return RedirectResponse(pending["redirect"], status_code=302, headers=headers)
        return HTMLResponse(
            '<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="refresh" content="3">'
            "<title>Authorize AIFindr DEV</title><h1>Connect the simulation gateway</h1>"
            "<p>AIFindr DEV requests permission to propose simulated transfers and read their status. "
            "This permission does not allow confirming or executing transfers.</p>"
            "<p>The operator must authorize this connection from the machine hosting the gateway:</p>"
            "<pre>cd backend\nuv run python -m app.oauth approve " + html.escape(request_id) + "</pre>"
            "<p>The request expires in five minutes. The page will continue after authorization.</p></html>",
            headers=headers,
        )

    async def load_authorization_code(self, client, authorization_code):
        with self.db() as db:
            data = self.get(db, "code", authorization_code)
        if not self.valid_grant(data, client.client_id):
            return None
        return AuthorizationCode(code=authorization_code, **data)

    def valid_grant(self, data, client_id=None):
        return bool(
            data
            and data.get("resource") == self.resource
            and data.get("subject") == self.subject
            and data.get("expires_at", 0) > time.time()
            and (client_id is None or data.get("client_id") == client_id)
        )

    def issue(self, db, client_id, scopes, family=None, refresh_expiry=None):
        family = family or secrets.token_hex(16)
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = int(time.time())
        # Rotation never extends the original family's absolute lifetime.
        refresh_expiry = refresh_expiry or now + 86400
        expires = min(now + 3600, refresh_expiry)
        grant = {
            "client_id": client_id,
            "scopes": scopes,
            "resource": self.resource,
            "subject": self.subject,
        }
        self.put(db, "access", access, {**grant, "expires_at": expires}, expires, family)
        self.put(db, "refresh", refresh, {**grant, "expires_at": refresh_expiry}, refresh_expiry, family)
        return OAuthToken(
            access_token=access,
            refresh_token=refresh,
            token_type="Bearer",
            expires_in=expires - now,
            scope=" ".join(scopes),
        )

    async def exchange_authorization_code(self, client, authorization_code):
        with self.db() as db:
            data = self.get(db, "code", authorization_code.code)
            if not self.valid_grant(data, client.client_id):
                raise TokenError("invalid_grant", "Code expired, consumed or bound to another resource")
            db.execute(
                "DELETE FROM oauth WHERE kind='code' AND key=?", (self.hashed(authorization_code.code),)
            )
            return self.issue(db, client.client_id, data["scopes"])

    def invalidate_refresh_replay(self, db, client_id, token):
        used = self.get(db, "used_refresh", token)
        if not self.valid_grant(used, client_id):
            return False
        row = db.execute(
            "SELECT family FROM oauth WHERE kind='used_refresh' AND key=?", (self.hashed(token),)
        ).fetchone()
        # Do not raise inside this transaction: the security revocation must
        # commit even though the caller subsequently returns invalid_grant.
        db.execute("DELETE FROM oauth WHERE family=?", (row["family"],))
        return True

    async def load_refresh_token(self, client, refresh_token):
        with self.db() as db:
            if self.invalidate_refresh_replay(db, client.client_id, refresh_token):
                return None
            data = self.get(db, "refresh", refresh_token)
        return RefreshToken(token=refresh_token, **data) if self.valid_grant(data, client.client_id) else None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        issued = None
        with self.db() as db:
            replay = self.invalidate_refresh_replay(db, client.client_id, refresh_token.token)
            data = self.get(db, "refresh", refresh_token.token)
            if not replay and self.valid_grant(data, client.client_id) and set(scopes) <= set(data["scopes"]):
                family = db.execute(
                    "SELECT family FROM oauth WHERE kind='refresh' AND key=?",
                    (self.hashed(refresh_token.token),),
                ).fetchone()[0]
                db.execute(
                    "UPDATE oauth SET kind='used_refresh' WHERE kind='refresh' AND key=?",
                    (self.hashed(refresh_token.token),),
                )
                db.execute("DELETE FROM oauth WHERE family=? AND kind='access'", (family,))
                issued = self.issue(db, client.client_id, scopes, family, data["expires_at"])
        if issued is None:
            raise TokenError("invalid_grant", "Refresh token expired, replayed or grant invalid")
        return issued

    async def load_access_token(self, token):
        with self.db() as db:
            data = self.get(db, "access", token)
        if not self.valid_grant(data) or SCOPE not in data["scopes"]:
            return None
        return AccessToken(token=token, **data)

    async def revoke_token(self, token):
        with self.db() as db:
            row = db.execute(
                "SELECT family FROM oauth WHERE key=? AND kind IN ('access','refresh')",
                (self.hashed(token.token),),
            ).fetchone()
            if row:
                db.execute("DELETE FROM oauth WHERE family=?", (row[0],))

    async def revoke_request(self, request):
        # SDK 2.1.1's revocation model requires client_secret even for public clients.
        # Retain SDK client authentication, but accept RFC 7009's optional secret.
        try:
            request = await self.normalize_basic_request(request)
            client = await ClientAuthenticator(self).authenticate_request(request)
        except AuthenticationError:
            return Response(status_code=401)
        form = await request.form()
        token_value = form.get("token")
        if not isinstance(token_value, str) or not token_value:
            return Response(status_code=400)
        token = await self.load_access_token(token_value) or await self.load_refresh_token(
            client, token_value
        )
        if token and token.client_id == client.client_id:
            await self.revoke_token(token)
        return Response(status_code=200, headers={"Cache-Control": "no-store"})

    async def normalize_basic_request(self, request):
        """SDK 2.1.1 requires body client_id even when RFC 6749 Basic supplies it.

        Supply only that identifier; SDK still verifies the original Basic secret,
        registration method, PKCE, code ownership, redirect and expiry.
        """
        form = await request.form()
        if any(len(form.getlist(key)) != 1 for key in form):
            raise AuthenticationError("Duplicate OAuth parameter")
        header = request.headers.get("authorization", "")
        if not header.startswith("Basic ") or "client_id" in form:
            return request
        try:
            credentials = base64.b64decode(header[6:], validate=True).decode("utf-8")
            client_id, _ = credentials.split(":", 1)
            client_id = unquote_plus(client_id)
            if not client_id:
                raise ValueError("Empty client")
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise AuthenticationError("Invalid Basic authentication") from exc
        body = urlencode([*form.multi_items(), ("client_id", client_id)]).encode()
        scope = dict(request.scope)
        scope["headers"] = [
            (key, value)
            for key, value in scope["headers"]
            if key.lower() not in {b"content-length", b"content-type"}
        ] + [
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"content-length", str(len(body)).encode()),
        ]

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        return Request(scope, receive)

    async def token_request(self, request):
        try:
            request = await self.normalize_basic_request(request)
        except AuthenticationError:
            return Response(status_code=401, headers={"Cache-Control": "no-store"})
        form = await request.form()
        if form.get("resource") not in (None, self.resource):
            return Response(status_code=400, headers={"Cache-Control": "no-store"})
        return await TokenHandler(self, ClientAuthenticator(self)).handle(request)


def main():
    import argparse

    from app.main import Settings

    parser = argparse.ArgumentParser(description="Explicit local consent for AIFindr MCP access")
    parser.add_argument("command", choices=["approve"])
    parser.add_argument("request_id")
    args = parser.parse_args()
    settings = Settings()
    if not settings.oauth_issuer_url:
        parser.exit(1, "Configure OAUTH_ISSUER_URL first\n")
    provider = OAuthProvider(settings.oauth_database_path, settings.oauth_issuer_url, settings.owner_id)
    provider.approve(args.request_id)
    print("OAuth connection approved for proposal/status only. No transfer has been confirmed.")


if __name__ == "__main__":
    main()
