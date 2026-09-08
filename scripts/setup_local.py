"""Create local-only secrets with exclusive creation and private initial modes."""

import os
from pathlib import Path
from secrets import token_urlsafe


def create_configuration(root: Path) -> None:
    backend = root / "backend/.env"
    frontend = root / "frontend/.env.local"
    if backend.exists() or frontend.exists():
        raise FileExistsError("Configuration already exists; leaving files unchanged.")
    reviewer, mcp, password, session = [token_urlsafe(36) for _ in range(4)]
    contents = {
        backend: f"MCP_TOKEN={mcp}\nREVIEWER_TOKEN={reviewer}\n",
        frontend: (
            "BACKEND_URL=http://127.0.0.1:8000\n"
            f"REVIEWER_TOKEN={reviewer}\nREVIEW_PASSWORD={password}\n"
            f"SESSION_SECRET={session}\nCOOKIE_SECURE=false\n"
        ),
    }
    created = []
    try:
        for path, content in contents.items():
            # O_EXCL also refuses symlinks and a competing setup process.
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
    except BaseException:
        # Roll back only files this invocation created, never existing config.
        for path in created:
            path.unlink(missing_ok=True)
        raise


def main():
    try:
        create_configuration(Path(__file__).resolve().parents[1])
    except OSError as exc:
        raise SystemExit("Setup failed; existing configuration was preserved. Check file paths and permissions.") from exc
    print("Local configuration created. Read REVIEW_PASSWORD from frontend/.env.local to sign in.")


if __name__ == "__main__":
    main()
