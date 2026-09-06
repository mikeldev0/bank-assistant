"""Create a synthetic proposal through the real MCP HTTP transport."""
import argparse
import asyncio
import os
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    args = parser.parse_args()
    config = dotenv_values(Path(__file__).resolve().parents[1] / "backend/.env")
    token = os.environ.get("MCP_TOKEN") or config["MCP_TOKEN"]
    async with httpx.AsyncClient(timeout=20, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"
    }) as client:
        async def rpc(method, params):
            response = await client.post(args.url, json={"jsonrpc": "2.0", "id": 1,
                                                        "method": method, "params": params})
            response.raise_for_status()
            body = response.json()
            if "error" in body or body.get("result", {}).get("isError"):
                raise RuntimeError("MCP request failed: " + str(body))
            return body["result"]
        await rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                  "clientInfo": {"name": "assessment-demo", "version": "1"}})
        result = await rpc("tools/call", {"name": "propose_transfer", "arguments": {
            "recipient": "Alex Demo", "destination": "DEMO-4821", "amount_cents": 12500,
            "concept": "Aportación al viaje · datos sintéticos", "idempotency_key": str(uuid4())}})
        print(result)
        print("Open the review UI and explicitly confirm. This script cannot execute the transfer.")


if __name__ == "__main__":
    asyncio.run(main())
