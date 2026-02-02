"""Microsoft Graph test utility: list chats + send a Teams chat message.

Auth model:
- Delegated device-code flow.
- Sends messages as the signed-in user.

Why not MSAL here?
- MSAL's device-flow call can hang in some corporate network environments.
- This script implements the device-code flow directly using `requests` with explicit timeouts.

Usage:
  set "GRAPH_TENANT=<tenant-guid>"
  set "GRAPH_CLIENT_ID=<app-client-id-guid>"

  # List recent chats
  .venv\Scripts\python -u send_test_teams_chat_graph.py --list --top 15

  # Send a message to a chat
  .venv\Scripts\python -u send_test_teams_chat_graph.py --send --chat-id <CHAT_ID> --message "hello"

Permissions (Delegated) recommended:
- User.Read
- Chat.ReadWrite

Note:
- This is a testing tool, not production auth plumbing.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPES = [
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Chat.ReadWrite",
]


@dataclass(frozen=True)
class GraphAuthConfig:
    tenant: str
    client_id: str
    token_cache_file: str


def _now_epoch() -> int:
    return int(time.time())


def _load_token_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _save_token_cache(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _cached_access_token(cache_path: Path) -> str | None:
    cached = _load_token_cache(cache_path)
    if not cached:
        return None

    token = str(cached.get("access_token") or "").strip()
    exp = int(cached.get("expires_at_epoch") or 0)
    if not token or exp <= _now_epoch() + 60:
        return None
    return token


def _device_code_start(*, tenant: str, client_id: str, scopes: list[str]) -> dict[str, Any]:
    """Start device-code flow and return the device-code payload."""

    scope_str = " ".join(scopes)
    device_code_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"

    print("Requesting device code...", flush=True)
    dc_resp = requests.post(
        device_code_url,
        data={"client_id": client_id, "scope": scope_str},
        timeout=15,
    )
    if dc_resp.status_code != 200:
        raise RuntimeError(f"devicecode failed: {dc_resp.status_code} {dc_resp.text}")

    dc = dc_resp.json()
    if not isinstance(dc, dict):
        raise RuntimeError(f"devicecode response not json object: {dc}")

    user_code = str(dc.get("user_code") or "")
    device_code = str(dc.get("device_code") or "")
    verify_uri = str(dc.get("verification_uri") or dc.get("verification_uri_complete") or "")
    message = str(dc.get("message") or "")

    if not user_code or not device_code:
        raise RuntimeError(f"devicecode response missing codes: {dc}")

    print("\n=== Microsoft Graph auth required (Teams chat) ===", flush=True)
    if message:
        print(message, flush=True)
    else:
        print(f"Go to: {verify_uri}", flush=True)
        print(f"Enter code: {user_code}", flush=True)

    return dc


def _device_code_finish(*, tenant: str, client_id: str, device_code: str, interval_s: int, expires_in_s: int) -> str:
    """Poll token endpoint until authorized (or timeout)."""

    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    deadline = _now_epoch() + int(expires_in_s)
    interval = max(1, int(interval_s))

    print("Polling token endpoint...", flush=True)
    last_status: str | None = None

    while _now_epoch() < deadline:
        time.sleep(interval)
        tok_resp = requests.post(
            token_url,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id,
                "device_code": device_code,
            },
            timeout=15,
        )

        if tok_resp.status_code == 200:
            tok = tok_resp.json()
            access_token = str(tok.get("access_token") or "")
            if not access_token:
                raise RuntimeError(f"token response missing access_token: {tok}")
            return access_token

        if tok_resp.status_code == 400:
            is_json = tok_resp.headers.get("content-type", "").startswith("application/json")
            err = tok_resp.json() if is_json else {}
            code = str(err.get("error") or "")
            desc = str(err.get("error_description") or "")

            # Print status changes so it doesn't look "stuck".
            status_line = code or f"http_400"
            if status_line != last_status:
                print(f"Token status: {status_line}", flush=True)
                if desc:
                    print(desc.splitlines()[0][:200], flush=True)
                last_status = status_line

            if code in ("authorization_pending", "slow_down"):
                if code == "slow_down":
                    interval = min(60, interval + 2)
                continue

            raise RuntimeError(f"token failed: {tok_resp.status_code} {tok_resp.text}")

        raise RuntimeError(f"token failed: {tok_resp.status_code} {tok_resp.text}")

    raise RuntimeError("Device code expired before authorization completed")


def _get_cfg(args: argparse.Namespace) -> GraphAuthConfig:
    tenant = (args.tenant or os.getenv("GRAPH_TENANT") or "").strip()
    client_id = (args.client_id or os.getenv("GRAPH_CLIENT_ID") or "").strip()

    if not tenant:
        raise ValueError("Tenant is required (use --tenant or set GRAPH_TENANT)")
    if not client_id:
        raise ValueError("Client ID is required (use --client-id or set GRAPH_CLIENT_ID)")

    cache_file = (
        args.token_cache_file
        or os.getenv("GRAPH_TOKEN_CACHE")
        or "graph_token_cache_teams_chat.json"
    ).strip()

    return GraphAuthConfig(tenant=tenant, client_id=client_id, token_cache_file=cache_file)


def _require_cached_token(cfg: GraphAuthConfig) -> str:
    cache_path = Path(cfg.token_cache_file)
    cached = _cached_access_token(cache_path)
    if cached:
        return cached
    raise RuntimeError(
        f"No valid cached token found at {cache_path}. Run --start-auth then --finish-auth first."
    )


def list_chats(*, token: str, top: int) -> list[dict[str, Any]]:
    url = f"{GRAPH_ENDPOINT}/me/chats?$top={int(top)}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Graph list chats failed: {resp.status_code} {resp.text}")

    payload = resp.json()
    return payload.get("value", []) if isinstance(payload, dict) else []


def send_chat_message(*, token: str, chat_id: str, message: str) -> None:
    if not chat_id.strip():
        raise ValueError("chat_id is required")

    url = f"{GRAPH_ENDPOINT}/chats/{chat_id}/messages"
    payload = {"body": {"contentType": "html", "content": message}}

    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=30,
    )

    if resp.status_code not in (201, 200):
        raise RuntimeError(f"Graph send chat message failed: {resp.status_code} {resp.text}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", help="Entra tenant id (or env GRAPH_TENANT)")
    p.add_argument("--client-id", help="Entra app client id (or env GRAPH_CLIENT_ID)")
    p.add_argument("--token-cache-file", help="Token cache file (or env GRAPH_TOKEN_CACHE)")
    p.add_argument(
        "--device-code-file",
        default="graph_device_code_teams_chat.json",
        help="Where to store the device-code payload between steps",
    )

    p.add_argument("--start-auth", action="store_true", help="Start device-code auth and save payload")
    p.add_argument("--finish-auth", action="store_true", help="Finish device-code auth (poll token) and cache token")

    p.add_argument("--list", action="store_true", help="List recent chats (requires cached token)")
    p.add_argument("--top", type=int, default=25, help="How many chats to list")

    p.add_argument("--send", action="store_true", help="Send a message (requires cached token)")
    p.add_argument("--chat-id", default="", help="Chat ID to send to")
    p.add_argument("--message", default="hello from ATC via Graph", help="Message content (HTML allowed)")

    args = p.parse_args()
    if not (args.start_auth or args.finish_auth or args.list or args.send):
        p.error("Choose one of: --start-auth, --finish-auth, --list, --send")

    cfg = _get_cfg(args)
    device_path = Path(str(args.device_code_file))

    if args.start_auth:
        dc = _device_code_start(tenant=cfg.tenant, client_id=cfg.client_id, scopes=GRAPH_SCOPES)
        _save_token_cache(device_path, dc)
        print(f"Saved device-code payload to: {device_path}")
        print("Now complete the browser auth, then run --finish-auth", flush=True)
        return 0

    if args.finish_auth:
        dc = _load_token_cache(device_path)
        if not dc:
            raise RuntimeError(f"No device-code payload found at {device_path}. Run --start-auth first.")

        token = _device_code_finish(
            tenant=cfg.tenant,
            client_id=cfg.client_id,
            device_code=str(dc.get('device_code') or ''),
            interval_s=int(dc.get('interval') or 5),
            expires_in_s=int(dc.get('expires_in') or 900),
        )

        cache_path = Path(cfg.token_cache_file)
        _save_token_cache(
            cache_path,
            {"access_token": token, "expires_at_epoch": _now_epoch() + 45 * 60},
        )
        print(f"OK: token cached to {cache_path}")
        return 0

    token = _require_cached_token(cfg)

    if args.list:
        chats = list_chats(token=token, top=args.top)
        if not chats:
            print("No chats returned.")
        for c in chats:
            chat_id = str(c.get("id", ""))
            chat_type = str(c.get("chatType", ""))
            topic = str(c.get("topic", ""))
            print(f"{chat_id}\t{chat_type}\t{topic}")

    if args.send:
        send_chat_message(token=token, chat_id=args.chat_id, message=args.message)
        print("OK: message sent")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
