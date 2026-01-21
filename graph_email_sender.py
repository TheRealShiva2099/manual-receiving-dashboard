"""Microsoft Graph email sender (device-code auth).

This module is intentionally tiny and boring.

Notes:
- Requires an Azure AD app registration with Mail.Send delegated permission.
- Uses MSAL token cache stored locally (see config).

We keep this separate from ATC logic (SRP).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import msal
import requests


GRAPH_SCOPE = ["https://graph.microsoft.com/Mail.Send"]
GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"


@dataclass(frozen=True)
class GraphConfig:
    tenant: str
    client_id: str
    sender: str
    token_cache_file: str


def _build_cache(cache_path: Path) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))
    return cache


def _persist_cache(cache: msal.SerializableTokenCache, cache_path: Path) -> None:
    if cache.has_state_changed:
        cache_path.write_text(cache.serialize(), encoding="utf-8")


def _acquire_token(cache: msal.SerializableTokenCache, cfg: GraphConfig) -> str:
    authority = f"https://login.microsoftonline.com/{cfg.tenant}"
    app = msal.PublicClientApplication(cfg.client_id, authority=authority, token_cache=cache)

    accounts = app.get_accounts()
    result: dict[str, Any] | None = None

    if accounts:
        result = app.acquire_token_silent(GRAPH_SCOPE, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=GRAPH_SCOPE)
        if "user_code" not in flow:
            raise RuntimeError(f"Failed to start device flow: {flow}")

        # User must complete this in a browser.
        print("\n=== Microsoft Graph auth required ===")
        print(flow["message"], flush=True)

        result = app.acquire_token_by_device_flow(flow)

    if not result or "access_token" not in result:
        raise RuntimeError(f"Failed to acquire Graph token: {result}")

    return str(result["access_token"])


def send_mail(
    *,
    cfg: GraphConfig,
    subject: str,
    html_body: str,
    to_recipients: list[str],
) -> None:
    """Send an email using Microsoft Graph.

    Uses /users/{sender}/sendMail.
    """

    if not cfg.client_id.strip():
        raise ValueError("Graph client_id is required (config.email_notifications.graph.client_id)")

    cache_path = Path(cfg.token_cache_file)
    cache = _build_cache(cache_path)
    token = _acquire_token(cache, cfg)
    _persist_cache(cache, cache_path)

    url = f"{GRAPH_ENDPOINT}/users/{cfg.sender}/sendMail"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in to_recipients],
        },
        "saveToSentItems": "true",
    }

    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=30,
    )

    if resp.status_code not in (202, 200):
        raise RuntimeError(f"Graph sendMail failed: {resp.status_code} {resp.text}")
