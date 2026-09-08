from contextlib import asynccontextmanager
from secrets import compare_digest
from typing import Annotated, Literal

from app.domain import DomainError, Proposal, Store
from app.oauth import SCOPE, OAuthProvider
from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from mcp.server import MCPServer
from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.responses import Response


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_path: str = "actions.db"
    mcp_token: str = Field(min_length=32)
    reviewer_token: str = Field(min_length=32)
    owner_id: str = "assessment-user"
    confirmation_ttl: int = Field(default=600, ge=1, le=3600)
    mcp_allowed_hosts: list[str] = ["localhost:*", "127.0.0.1:*"]
    oauth_issuer_url: str | None = None
    oauth_database_path: str = "oauth.db"

    @model_validator(mode="after")
    def separate_roles(self):
        if self.mcp_token == self.reviewer_token:
            raise ValueError("MCP and reviewer must have different credentials")
        return self


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["confirm", "reject"]


class MCPAuth:
    def __init__(self, app, token, oauth=None):
        self.app, self.token = app, token
        self.oauth = oauth

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            expected = f"Bearer {self.token}".encode()
            if not compare_digest(headers.get(b"authorization", b""), expected):
                auth = headers.get(b"authorization", b"").decode("latin1")
                verified = (
                    await self.oauth.load_access_token(auth[7:])
                    if self.oauth and auth.startswith("Bearer ")
                    else None
                )
                if verified is None:
                    challenge = (
                        {
                            "WWW-Authenticate": 'Bearer resource_metadata="'
                            + self.oauth.issuer
                            + '/.well-known/oauth-protected-resource/mcp", scope="'
                            + SCOPE
                            + '"'
                        }
                        if self.oauth
                        else {}
                    )
                    await Response(status_code=401, headers=challenge)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    store = Store(settings.database_path, settings.confirmation_ttl)
    mcp = MCPServer(
        "Bank Assistant · Safe Actions",
        instructions="Propose simulated transfers only. A human must confirm in the review UI. Never claim execution before status is executed.",
    )

    @mcp.tool()
    def propose_transfer(
        recipient: str,
        destination: str,
        amount_cents: Annotated[int, Field(strict=True)],
        concept: str,
        idempotency_key: str,
    ) -> dict:
        """Propose a EUR simulation, maximum 100000 cents. Destination must be DEMO-xxxx. Reuse idempotency_key on retries. Cannot confirm or execute."""
        return store.propose(
            settings.owner_id,
            Proposal(
                recipient=recipient,
                destination=destination,
                amount_cents=amount_cents,
                concept=concept,
                idempotency_key=idempotency_key,
            ),
        )

    @mcp.tool()
    def get_transfer_status(action_id: str) -> dict:
        """Read the authoritative status and audit of a simulated transfer."""
        return store.get(settings.owner_id, action_id)

    mcp_app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=settings.mcp_allowed_hosts
        ),
    )

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Bank Assistant Safe Actions", version="1.0.0", lifespan=lifespan)
    app.state.store, app.state.mcp = store, mcp
    oauth = None
    if settings.oauth_issuer_url:
        from starlette.routing import Route

        oauth = OAuthProvider(settings.oauth_database_path, settings.oauth_issuer_url)
        app.state.oauth = oauth
        app.router.routes.append(Route("/revoke", oauth.revoke_request, methods=["POST"]))
        app.router.routes.extend(
            create_auth_routes(
                oauth,
                AnyHttpUrl(oauth.issuer),
                client_registration_options=ClientRegistrationOptions(
                    enabled=True,
                    valid_scopes=[SCOPE],
                    default_scopes=[SCOPE],
                ),
                revocation_options=RevocationOptions(enabled=True),
            )
        )
        app.router.routes.extend(
            create_protected_resource_routes(
                AnyHttpUrl(oauth.resource),
                [AnyHttpUrl(oauth.issuer)],
                [SCOPE],
                "Bank Assistant simulations",
            )
        )
        app.router.routes.append(Route("/consent", oauth.consent, methods=["GET"]))

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    def reviewer(authorization: str = Header(default="")):
        if not compare_digest(authorization, f"Bearer {settings.reviewer_token}"):
            raise DomainError("No autorizado.", 401)
        return settings.owner_id

    @app.get("/health")
    def health():
        return {"status": "ok", "simulation_only": True}

    @app.get("/actions")
    def actions(owner: str = Depends(reviewer)):
        return store.list(owner)

    @app.get("/actions/{action_id}")
    def action(action_id: str, owner: str = Depends(reviewer)):
        return store.get(owner, action_id)

    @app.post("/actions/{action_id}/decision")
    def decide(action_id: str, body: Decision, owner: str = Depends(reviewer)):
        return store.decide(owner, action_id, body.fingerprint, body.decision == "confirm")

    app.mount("/", MCPAuth(mcp_app, settings.mcp_token, oauth))
    return app
