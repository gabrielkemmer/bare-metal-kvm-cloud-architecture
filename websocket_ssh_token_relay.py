"""
Production Pattern: 30-Second Single-Use Token WebSocket-to-SSH Relay (Port 22)
Separates long-lived WebSocket terminal streaming from the HTTP control plane.
The HTTP API verifies ownership and mints a 30s one-time token bound to the
server-side resolved VPS IP (or GPU pod host:port); the relay trusts the token,
never browser-supplied target parameters, and connects over standard SSH Port 22.
"""

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Mapping

TERMINAL_TOKEN_TTL_SECONDS = 30


def issue_single_use_terminal_token(
    *,
    token_store: Any,
    authenticated_client: Mapping[str, Any],
    ssh_port: int = 22,
) -> dict[str, Any]:
    """
    Mint a short-lived, single-use token authorizing one WebSocket terminal session
    to the customer's own VPS IP on Port 22.
    """
    vps_ip = (authenticated_client.get("ip") or "").strip()
    if not vps_ip:
        raise ValueError("VPS does not have an assigned IP address.")

    token = secrets.token_urlsafe(32)
    token_store.insert_one({
        "token": token,
        "ip": vps_ip,
        "port": ssh_port,
        "domain": authenticated_client.get("domain"),
        "created_at": datetime.now(timezone.utc),
        "used": False,
    })
    return {
        "token": token,
        "ttl_seconds": TERMINAL_TOKEN_TTL_SECONDS,
        "ws_path": f"/ws/terminal?token={token}",
    }


def consume_terminal_token_atomically(token_store: Any, raw_token: str) -> dict[str, Any]:
    """
    Executed by the standalone WebSocket relay process (`web_terminal.py`).
    Atomically transitions `used: False -> True` and enforces the 30-second TTL
    before opening the SSH Port 22 connection to `doc['ip']`.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=TERMINAL_TOKEN_TTL_SECONDS)
    doc = token_store.find_one_and_update(
        {
            "token": raw_token,
            "used": False,
            "created_at": {"$gte": cutoff},
        },
        {"$set": {"used": True, "consumed_at": datetime.now(timezone.utc)}},
    )
    if not doc:
        raise PermissionError("Invalid, expired, or already-used terminal token.")
    return {"ip": doc["ip"], "port": int(doc.get("port", 22))}
