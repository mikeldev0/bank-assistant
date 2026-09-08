"""Private artifacts and authenticated, bounded integration clients."""

import json
import os
import tempfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import httpx2
from dotenv import dotenv_values
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "private"


def now():
    return datetime.now(UTC).isoformat()


def config():
    # Compatibility with the user's existing file. Only CLI code imports this module.
    front = {**dotenv_values(ROOT / "frontend/.env"), **dotenv_values(ROOT / "frontend/.env.local")}
    front = {k: v for k, v in front.items() if k.startswith("AIFINDR_") and v}
    root = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v}
    return {**front, **root, **dotenv_values(ROOT / "backend/.env"), **os.environ}


def private_path(value):
    path = Path(value).resolve()
    if not path.is_relative_to(PRIVATE.resolve()) or path == PRIVATE.resolve():
        raise ValueError("Evaluation artifacts must be inside the repository private/ directory")
    return path


def save(path, value):
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def gateway_url(url):
    parts = urlsplit(url)
    local = parts.hostname in {"127.0.0.1", "localhost", "::1"}
    if (parts.scheme != "https" and not (local and parts.scheme == "http")) or not parts.hostname:
        raise ValueError("MCP requires HTTPS except on loopback")
    if parts.username or parts.password or parts.query or parts.fragment or parts.path != "/mcp":
        raise ValueError("Use a clean /mcp URL without credentials, query or fragment")
    return url


@asynccontextmanager
async def gateway(url):
    token = config().get("MCP_TOKEN")
    if not token or len(token) < 32:
        raise ValueError("Set MCP_TOKEN in backend/.env")
    async with (
        httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, timeout=20, follow_redirects=False
        ) as client,
        streamable_http_client(gateway_url(url), http_client=client) as streams,
        ClientSession(*streams, read_timeout_seconds=20) as session,
    ):
        await session.initialize()
        yield session


async def call(session, name, arguments):
    result = await session.call_tool(name, arguments)
    if result.is_error:
        raise ValueError("Gateway rejected tool call; inspect the local gateway privately")
    if result.structured_content is not None:
        return result.structured_content
    for block in result.content:
        if block.type == "text":
            return json.loads(block.text)
    raise ValueError("Gateway returned no structured result")


async def conversation(conversation_id, settings=None, transport=None):
    """Only the documented read endpoint; never guess private chat/write routes."""
    settings = settings or config()
    key, org = settings.get("AIFINDR_API_KEY"), settings.get("AIFINDR_ORGANIZATION_ID")
    if not key or not org:
        raise ValueError("Set AIFINDR_API_KEY and AIFINDR_ORGANIZATION_ID in root .env")
    base = settings.get("AIFINDR_API_BASE_URL", "https://api-dev.saas.aifindr.ai").rstrip("/")
    if base != "https://api-dev.saas.aifindr.ai":
        raise ValueError("This assessment client is restricted to AIFindr DEV")
    async with httpx.AsyncClient(
        base_url=base,
        timeout=30,
        follow_redirects=False,
        transport=transport,
        headers={"Authorization": f"Bearer {key}", "X-Organization-Id": org},
    ) as client:
        response = await client.get("/api/private/conversations/" + quote(conversation_id, safe=""))
    if response.status_code != 200:
        raise ValueError(
            f"Private conversation read failed (HTTP {response.status_code}); no response logged"
        )
    body = response.json()
    if not isinstance(body, dict) or body.get("id") != conversation_id or not body.get("messages"):
        raise ValueError("Private API response does not match the documented conversation schema")
    return body


async def project_conversations(page=1, per_page=20, settings=None, transport=None):
    """Documented private list endpoint; no automatic traversal of project history."""
    settings = settings or config()
    if not 1 <= per_page <= 100 or page < 1:
        raise ValueError("Invalid pagination")
    key, org, project = (
        settings.get(k) for k in ["AIFINDR_API_KEY", "AIFINDR_ORGANIZATION_ID", "AIFINDR_PROJECT_ID"]
    )
    if not all([key, org, project]):
        raise ValueError("Set AIFindr API key, organization and project IDs")
    base = settings.get("AIFINDR_API_BASE_URL", "https://api-dev.saas.aifindr.ai").rstrip("/")
    if base != "https://api-dev.saas.aifindr.ai":
        raise ValueError("This assessment client is restricted to AIFindr DEV")
    async with httpx.AsyncClient(
        base_url=base,
        timeout=30,
        follow_redirects=False,
        transport=transport,
        headers={"Authorization": f"Bearer {key}", "X-Organization-Id": org},
    ) as client:
        response = await client.get(
            "/api/private/projects/" + quote(project, safe="") + "/conversations",
            params={"page": page, "perPage": per_page},
        )
    if response.status_code != 200:
        raise ValueError(f"Private list failed (HTTP {response.status_code}); no response logged")
    body = response.json()
    if (
        not isinstance(body, dict)
        or not isinstance(body.get("items"), list)
        or not isinstance(body.get("pagination"), dict)
    ):
        raise TypeError("Private API response does not match the documented pagination schema")
    return body
