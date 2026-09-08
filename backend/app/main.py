import logging
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server import MCPServer
from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.responses import Response

from app.domain import DomainError, Proposal, Store
from app.oauth import SCOPE, OAuthProvider
from app.security import TOKEN_PATTERN, bearer_token, token_matches


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_path: str = "actions.db"
    mcp_token: str = Field(min_length=32, max_length=256, pattern=TOKEN_PATTERN)
    reviewer_token: str = Field(min_length=32, max_length=256, pattern=TOKEN_PATTERN)
    owner_id: str = Field(default="assessment-user", min_length=1, max_length=128)
    confirmation_ttl: int = Field(default=600, ge=1, le=3600)
    mcp_allowed_hosts: list[str] = ["localhost:*", "127.0.0.1:*"]
    oauth_issuer_url: str | None = None
    oauth_database_path: str = "oauth.db"
    review_base_url: str = "http://127.0.0.1:3000"

    @model_validator(mode="after")
    def separate_roles(self):
        if self.mcp_token == self.reviewer_token:
            raise ValueError("MCP and reviewer must have different credentials")
        review = urlsplit(self.review_base_url)
        _ = review.port  # Validate malformed/out-of-range ports at startup.
        if (review.scheme != "https" and not
            (review.scheme == "http" and review.hostname in {"localhost", "127.0.0.1"})) or (
            not review.hostname or review.username or review.password or review.query or review.fragment
            or review.path not in {"", "/"}
        ):
            raise ValueError("Review URL must be a clean HTTPS origin or loopback HTTP")
        return self


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["confirm", "reject"]


class MCPAuth:
    def __init__(self, app, token, security, oauth=None):
        self.app, self.token = app, token
        self.security = TransportSecurityMiddleware(security)
        self.oauth = oauth

    async def __call__(self, scope, receive, send):
        async def observed_send(message):
            if message["type"] == "http.response.start":
                logging.getLogger("uvicorn.error").info(
                    "MCP transport %s status=%s", scope.get("method"), message["status"]
                )
            await send(message)

        if scope["type"] == "http":
            token = bearer_token(Request(scope, receive).headers)
            if not token_matches(token, self.token):
                verified = await self.oauth.load_access_token(token) if self.oauth and token else None
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
                    await Response(status_code=401, headers=challenge)(scope, receive, observed_send)
                    return
            if scope.get("method") == "GET" and scope.get("path") == "/mcp":
                # This stateless request/response gateway has no server notifications.
                # An idle GET SSE stream can stall discovery behind buffering proxies.
                error = await self.security.validate_request(Request(scope, receive))
                response = error or Response(status_code=405, headers={"Allow": "POST"})
                await response(scope, receive, observed_send)
                return
        await self.app(scope, receive, observed_send)


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    store = Store(settings.database_path, settings.confirmation_ttl)
    def review_link(action):
        return {**action, "review_url": settings.review_base_url.rstrip("/") + "/?action=" + action["id"]}
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
        return review_link(store.propose(
            settings.owner_id,
            Proposal(
                recipient=recipient,
                destination=destination,
                amount_cents=amount_cents,
                concept=concept,
                idempotency_key=idempotency_key,
            ),
        ))

    @mcp.tool()
    def get_transfer_status(action_id: str) -> dict:
        """Read the authoritative status and audit of a simulated transfer."""
        return review_link(store.get(settings.owner_id, action_id))

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=settings.mcp_allowed_hosts
    )
    mcp_app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=security,
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

        oauth = OAuthProvider(settings.oauth_database_path, settings.oauth_issuer_url, settings.owner_id)
        app.state.oauth = oauth
        app.router.routes.append(Route("/token", oauth.token_request, methods=["POST"]))
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

    def reviewer(request: Request):
        if not token_matches(bearer_token(request.headers), settings.reviewer_token):
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

    app.mount("/", MCPAuth(mcp_app, settings.mcp_token, security, oauth))
    return app
