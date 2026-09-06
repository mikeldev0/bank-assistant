"""Generate local-only secrets without overwriting existing configuration."""
from pathlib import Path
from secrets import token_urlsafe

root = Path(__file__).resolve().parents[1]
backend = root / "backend/.env"
frontend = root / "frontend/.env.local"
if backend.exists() or frontend.exists():
    raise SystemExit("Configuration already exists; leaving files unchanged.")
reviewer, mcp, password, session = [token_urlsafe(36) for _ in range(4)]
backend.write_text(f"MCP_TOKEN={mcp}\nREVIEWER_TOKEN={reviewer}\n")
frontend.write_text(f"BACKEND_URL=http://127.0.0.1:8000\nREVIEWER_TOKEN={reviewer}\nREVIEW_PASSWORD={password}\nSESSION_SECRET={session}\nCOOKIE_SECURE=false\n")
backend.chmod(0o600)
frontend.chmod(0o600)
print("Local configuration created. Read REVIEW_PASSWORD from frontend/.env.local to sign in.")
