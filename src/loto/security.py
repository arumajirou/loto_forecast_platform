from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

ROLE_ORDER = {"viewer": 0, "researcher": 1, "operator": 2, "approver": 3, "administrator": 4}


@dataclass(frozen=True)
class Identity:
    username: str
    role: str


def parse_tokens(raw: str | None = None) -> dict[str, Identity]:
    """Parse `token=username:role,token2=user2:viewer` without exposing secrets."""
    raw = raw if raw is not None else os.environ.get("LOTO_API_TOKENS", "")
    result: dict[str, Identity] = {}
    for item in filter(None, (x.strip() for x in raw.split(","))):
        token, assignment = item.split("=", 1)
        username, role = assignment.split(":", 1)
        if role not in ROLE_ORDER:
            raise ValueError(f"unknown role: {role}")
        result[hashlib.sha256(token.encode()).hexdigest()] = Identity(username, role)
    return result


def authenticate(token: str, token_map: dict[str, Identity]) -> Identity:
    digest = hashlib.sha256(token.encode()).hexdigest()
    for expected, identity in token_map.items():
        if hmac.compare_digest(digest, expected):
            return identity
    raise PermissionError("invalid API token")


def require_role(identity: Identity, minimum: str) -> None:
    if ROLE_ORDER[identity.role] < ROLE_ORDER[minimum]:
        raise PermissionError(f"role {identity.role} cannot perform operation requiring {minimum}")
