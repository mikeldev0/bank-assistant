# OAuth for the assessment MCP

AIFindr DEV's Custom MCP interface requires OAuth. The gateway now exposes the
MCP SDK authorization and protected-resource discovery endpoints when
`OAUTH_ISSUER_URL` is set to the public origin. Add that hostname to
`MCP_ALLOWED_HOSTS` and restart the backend with access logging disabled:

```bash
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

Register the `/mcp` URL in the project's Settings, then connect OAuth. Dynamic
registration accepts HTTPS callbacks only on the AIFindr DEV API and Hub origins.
The consent page provides a five-minute request identifier. The local operator
explicitly approves it with the command displayed there. This grants only
`transfers:propose-read`, never human confirmation authority.

The SDK validates client credentials, redirect matching and S256 PKCE. Codes are
single-use and expire in 60 seconds. Opaque access tokens expire in one hour;
refresh tokens expire in one day and rotate with their token family. Tokens are
stored by hash in a separate mode-0600 SQLite database. Resource checks restrict
access tokens to this gateway. Client registrations expire after seven days.
The local MCP token remains supported for diagnostic scripts.

This is a single-project assessment provider with local operator consent, not a
general identity service. Persistent hosting needs stable HTTPS, storage and
proxy rate limits. Changing a temporary tunnel origin requires reconnecting OAuth.

The custom revocation handler retains SDK client authentication and accepts the
optional secret for public clients, working around the SDK 2.1.1 revocation model.
Tests cover wrong PKCE, forbidden callbacks, code replay, rotation, revocation,
audience rejection and the separation from transfer review credentials.

Reference: [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization).
