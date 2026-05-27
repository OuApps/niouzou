"""Opaque cursor helpers for keyset pagination.

A cursor is a base64url-encoded JSON object. Each endpoint decides which keys
it carries (e.g. feed uses ``rank`` + ``id``). Encoding keeps the wire format
opaque to clients, as promised in docs/API_SPEC.md.
"""

import base64
import json

from niouzou.errors import bad_request


def encode_cursor(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (ValueError, json.JSONDecodeError) as exc:
        raise bad_request("Invalid cursor") from exc
