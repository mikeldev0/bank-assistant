"""Verify read-only project access without printing private conversation data."""

import argparse
import asyncio
import json

from evaluations.support import now, project_conversations, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="private/aifindr-api-check.json")
    args = parser.parse_args()
    try:
        data = asyncio.run(project_conversations(per_page=1))
        report = {
            "checked_at": now(),
            "private_project_read": "passed",
            "http_status": 200,
            "returned_items": len(data["items"]),
            "aifindr_mcp_connection": "not_verified",
        }
        save(args.output, report)
        print(json.dumps(report, indent=2))
    except Exception:  # noqa: BLE001 -- Do not print third-party exception bodies or credentials.
        parser.exit(
            1,
            "AIFindr check failed: verify DEV API key, project, organization and network. No secrets logged.\n",
        )


if __name__ == "__main__":
    main()
