from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class EmailState:
    # delivery_number -> epoch timestamp (when emailed)
    emailed_deliveries: dict[str, int]
    # timestamps of sent emails (epoch seconds) for rate limiting
    sent_email_timestamps: list[int]


def load_email_state(path: Path) -> EmailState:
    if not path.exists():
        return EmailState(emailed_deliveries={}, sent_email_timestamps=[])

    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return EmailState(emailed_deliveries={}, sent_email_timestamps=[])

    ed = payload.get("emailed_deliveries", {})
    st = payload.get("sent_email_timestamps", [])

    if not isinstance(ed, dict):
        ed = {}
    if not isinstance(st, list):
        st = []

    ed2: dict[str, int] = {}
    for k, v in ed.items():
        try:
            ed2[str(k)] = int(v)
        except Exception:
            continue

    st2: list[int] = []
    for x in st:
        try:
            st2.append(int(x))
        except Exception:
            continue

    return EmailState(emailed_deliveries=ed2, sent_email_timestamps=st2)


def save_email_state(path: Path, state: EmailState) -> None:
    payload = {
        "emailed_deliveries": state.emailed_deliveries,
        "sent_email_timestamps": state.sent_email_timestamps,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def prune_email_state(state: EmailState, retention_days: int = 14) -> None:
    now = int(time.time())
    cutoff = now - retention_days * 86400
    state.emailed_deliveries = {k: v for k, v in state.emailed_deliveries.items() if v >= cutoff}

    hour_ago = now - 3600
    state.sent_email_timestamps = [t for t in state.sent_email_timestamps if t >= hour_ago]


def can_send_email(state: EmailState, max_per_hour: int) -> bool:
    prune_email_state(state)
    return len(state.sent_email_timestamps) < int(max_per_hour)


def mark_email_sent(state: EmailState) -> None:
    state.sent_email_timestamps.append(int(time.time()))


def has_emailed_delivery(state: EmailState, delivery_number: str) -> bool:
    return str(delivery_number) in state.emailed_deliveries


def mark_delivery_emailed(state: EmailState, delivery_number: str) -> None:
    state.emailed_deliveries[str(delivery_number)] = int(time.time())
