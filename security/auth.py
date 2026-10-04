"""Authentication (who are you?) and authorization (what may you do?).

Prototype: static bearer tokens from AKILI_TOKENS. Production: swap identify()
for OAuth/OIDC token validation; authorize() stays the same.

AKILI_TOKENS = {"<token>": {"name": "denise", "role": "lead", "clients": ["*"]}, ...}
"""
import hmac
import json
import os
from dataclasses import dataclass

ROLE_SCOPES = {
    "lead": {"client:read", "ops:read", "memory:write"},
    "client_lead": {"client:read", "ops:read"},
    "ops": {"ops:read"},
}


@dataclass(frozen=True)
class Identity:
    name: str
    role: str
    clients: frozenset  # client ids, or {"*"} for all
    scopes: frozenset


def load_tokens() -> dict:
    return json.loads(os.environ.get("AKILI_TOKENS", "{}"))


def identify(auth_header: str, tokens: dict) -> Identity | None:
    if not auth_header.lower().startswith("bearer "):
        return None
    supplied = auth_header[7:].strip()
    found = None
    for token, who in tokens.items():  # no early exit, constant-time compares
        if hmac.compare_digest(supplied, token):
            found = who
    if not found:
        return None
    role = found.get("role", "ops")
    return Identity(
        name=found["name"],
        role=role,
        clients=frozenset(c.lower() for c in found.get("clients", [])),
        scopes=frozenset(ROLE_SCOPES.get(role, set())),
    )


def visible_clients(ident: Identity, known: set[str]) -> set[str]:
    return set(known) if "*" in ident.clients else set(known) & ident.clients


def authorize(ident: Identity, scope: str | None, client: str | None, known: set[str]) -> str | None:
    """Raise PermissionError unless ident holds `scope` and may see `client`.

    Returns the normalised client id (or None when no client was asked for).
    """
    if scope and scope not in ident.scopes:
        raise PermissionError(f"Role '{ident.role}' lacks scope '{scope}'")
    if client is None:
        return None
    c = client.strip().lower().replace(" ", "")
    if c not in visible_clients(ident, known):
        raise PermissionError(f"No access to '{client}'. Your clients: {sorted(visible_clients(ident, known))}")
    return c
