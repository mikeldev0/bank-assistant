"""Read-only MCP diagnostic. A successful probe is not an AIFindr agent integration."""

import argparse
import asyncio
import json

import httpx

from evaluations.support import call, gateway, gateway_url, now, save


async def check(url, action_id=None):
    gateway_url(url)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    if response.status_code != 401:
        raise ValueError("Unauthenticated MCP requests must return 401")
    async with gateway(url) as session:
        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        if names != {"propose_transfer", "get_transfer_status"} or listed.next_cursor:
            raise ValueError("Unexpected tool list; expected only proposal and status")
        state = await call(session, "get_transfer_status", {"action_id": action_id}) if action_id else None
    return {
        "checked_at": now(),
        "https": url.startswith("https://"),
        "unauthenticated_status": 401,
        "authenticated_initialize": "passed",
        "tools": sorted(names),
        "status_lookup": "passed" if state else "not_requested",
        "action_state": state["status"] if state else None,
        "aifindr_connection": "not_verified",
        "scope": "Read-only transport and discovery probe",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--action-id")
    parser.add_argument("--output", default="private/integration-check.json")
    args = parser.parse_args()
    try:
        result = asyncio.run(check(args.url, args.action_id))
        save(args.output, result)
        print(json.dumps(result, indent=2))
    except Exception:  # noqa: BLE001 -- Do not print third-party exception bodies or credentials.
        parser.exit(
            1,
            "Integration check failed: verify URL, allowed hosts, token and gateway availability. No credentials logged.\n",
        )


if __name__ == "__main__":
    main()
