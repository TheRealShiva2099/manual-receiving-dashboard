from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class TeamsWebhookConfig:
    webhook_url: str


def post_teams_message(*, cfg: TeamsWebhookConfig, title: str, lines: list[str]) -> None:
    """Post a simple message to a Teams channel via Incoming Webhook.

    This does NOT require Graph admin consent, but it can only post to a channel
    that has a webhook configured.

    Message format: MessageCard (legacy) for max compatibility.
    """

    url = str(cfg.webhook_url or "").strip()
    if not url:
        raise ValueError("Teams webhook_url is empty")

    text = "\n".join([f"- {x}" for x in lines if str(x).strip()])

    payload: dict[str, Any] = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "themeColor": "0071CE",
        "title": title,
        "text": text,
    }

    resp = requests.post(
        url,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Teams webhook failed ({resp.status_code}): {resp.text[:500]}")
