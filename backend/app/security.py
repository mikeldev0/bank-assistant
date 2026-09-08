"""Strict, shared parsing for the two independent bearer-authenticated roles."""

import re
from secrets import compare_digest

from starlette.datastructures import Headers

TOKEN_PATTERN = r"^[A-Za-z0-9._~+/-]+=*$"
_BEARER = re.compile(r"(?i:Bearer) ([A-Za-z0-9._~+/-]+=*)")


def bearer_token(headers: Headers) -> str | None:
    values = headers.getlist("authorization")
    if len(values) != 1:
        return None
    match = _BEARER.fullmatch(values[0])
    return match[1] if match else None


def token_matches(token: str | None, expected: str) -> bool:
    # The parser and settings constrain both operands to ASCII bearer tokens.
    return token is not None and compare_digest(token.encode("ascii"), expected.encode("ascii"))
