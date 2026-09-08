"""Assessment OAuth provider: SDK protocol handlers, explicit local operator consent.

Single project only. Local approval is separate from transfer confirmation. Tokens
are opaque, expire, are audience-bound and are stored by hash in a private SQLite DB.
"""

import hashlib
import html
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

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
from starlette.responses import HTMLResponse, RedirectResponse, Response

SCOPE = "transfers:propose-read"
CALLBACK_ORIGINS = {"https://api-dev.saas.aifindr.ai", "https://hub-dev.aifindr.ai"}


class OAuthProvider:
    def __init__(self, path, issuer):
        self.path, self.issuer = path, issuer.rstrip("/")
        self.resource = self.issuer + "/mcp"
        parts = urlsplit(self.issuer)
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
                    db.execute("DELETE FROM oauth WHERE expires < ?", (time.time(),))
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
                subject="assessment-user",
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
            '<!doctype html><html lang="es"><meta charset="utf-8"><meta http-equiv="refresh" content="3">'
            "<title>Autorizar AIFindr DEV</title><h1>Conectar el gateway de simulaciones</h1>"
            "<p>AIFindr DEV solicita permiso para proponer transferencias simuladas y consultar su estado. "
            "Este permiso no permite confirmar ni ejecutar transferencias.</p>"
            "<p>El operador debe autorizar esta conexión desde el equipo que aloja el gateway:</p>"
            "<pre>cd backend\nuv run python -m app.oauth approve " + html.escape(request_id) + "</pre>"
            "<p>La solicitud caduca en cinco minutos. La página continuará al recibir la autorización.</p></html>",
            headers=headers,
        )

    async def load_authorization_code(self, client, authorization_code):
        with self.db() as db:
            data = self.get(db, "code", authorization_code)
        if not data or data["client_id"] != client.client_id:
            return None
        return AuthorizationCode(code=authorization_code, **data)

    def issue(self, db, client_id, scopes, family=None):
        family = family or secrets.token_hex(16)
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expires = int(time.time()) + 3600
        self.put(
            db,
            "access",
            access,
            {
                "client_id": client_id,
                "scopes": scopes,
                "expires_at": expires,
                "resource": self.resource,
                "subject": "assessment-user",
            },
            expires,
            family,
        )
        refresh_expiry = int(time.time()) + 86400
        self.put(
            db,
            "refresh",
            refresh,
            {
                "client_id": client_id,
                "scopes": scopes,
                "expires_at": refresh_expiry,
                "subject": "assessment-user",
            },
            refresh_expiry,
            family,
        )
        return OAuthToken(
            access_token=access,
            refresh_token=refresh,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(scopes),
        )

    async def exchange_authorization_code(self, client, authorization_code):
        with self.db() as db:
            data = self.get(db, "code", authorization_code.code)
            if not data or data["client_id"] != client.client_id:
                raise TokenError("invalid_grant", "Code expired or already consumed")
            db.execute(
                "DELETE FROM oauth WHERE kind='code' AND key=?", (self.hashed(authorization_code.code),)
            )
            return self.issue(db, client.client_id, data["scopes"])

    async def load_refresh_token(self, client, refresh_token):
        with self.db() as db:
            data = self.get(db, "refresh", refresh_token)
        return (
            RefreshToken(token=refresh_token, **data)
            if data and data["client_id"] == client.client_id
            else None
        )

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        with self.db() as db:
            data = self.get(db, "refresh", refresh_token.token)
            if not data or data["client_id"] != client.client_id or not set(scopes) <= set(data["scopes"]):
                raise TokenError("invalid_grant", "Refresh token expired, consumed or scope invalid")
            family = db.execute(
                "SELECT family FROM oauth WHERE kind='refresh' AND key=?", (self.hashed(refresh_token.token),)
            ).fetchone()[0]
            db.execute("DELETE FROM oauth WHERE family=?", (family,))
            return self.issue(db, client.client_id, scopes, family)

    async def load_access_token(self, token):
        with self.db() as db:
            data = self.get(db, "access", token)
        if not data or data["resource"] != self.resource or SCOPE not in data["scopes"]:
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
            client = await ClientAuthenticator(self).authenticate_request(request)
        except AuthenticationError:
            return Response(status_code=401)
        form = await request.form()
        token_value = form.get("token")
        if not isinstance(token_value, str) or not token_value:
            return Response(status_code=400)
        token = await self.load_access_token(token_value) or await self.load_refresh_token(client, token_value)
        if token and token.client_id == client.client_id:
            await self.revoke_token(token)
        return Response(status_code=200, headers={"Cache-Control": "no-store"})


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
    provider = OAuthProvider(settings.oauth_database_path, settings.oauth_issuer_url)
    provider.approve(args.request_id)
    print("OAuth connection approved for proposal/status only. No transfer has been confirmed.")


if __name__ == "__main__":
    main()
