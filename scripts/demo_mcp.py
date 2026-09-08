"""Create a synthetic proposal through the authenticated MCP client."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4


async def propose_demo(url):
    from evaluations.support import call, gateway

    async with gateway(url) as session:
        return await call(
            session,
            "propose_transfer",
            {
                "recipient": "Alex Demo",
                "destination": "DEMO-4821",
                "amount_cents": 12500,
                "concept": "Synthetic travel contribution",
                "idempotency_key": str(uuid4()),
            },
        )


def main():
    # Also support the documented direct invocation from the backend directory.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    args = parser.parse_args()
    try:
        proposal = asyncio.run(propose_demo(args.url))
    except Exception:
        parser.exit(1, "MCP demo failed. Check the URL, credentials and local server privately.\n")
    print(json.dumps(proposal, ensure_ascii=False, indent=2))
    print("Open review_url and explicitly confirm. This script cannot execute the transfer.")


if __name__ == "__main__":
    main()
