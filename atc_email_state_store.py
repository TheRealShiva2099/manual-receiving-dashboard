from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class EmailState:
    # delivery_number -> epoch timestamp (when a notification was produced)
    emailed_deliveries: dict[str, int]

    # Legacy: timestamps of sent emails (epoch seconds) for rate limiting
    sent_email_timestamps: list[int]

    # New: rate-limiting buckets per channel (email/teams/etc)
    sent_timestamps_by_channel: dict[str, list[int]]


def load_email_state(path: Path) -> EmailState:
    if not path.exists():
        return EmailState(emailed_deliveries={}, sent_email_timestamps=[], sent_timestamps_by_channel={})

    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return EmailState(emailed_deliveries={}, sent_email_timestamps=[], sent_timestamps_by_channel={})

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

    by = payload.get("sent_timestamps_by_channel", {})
    if not isinstance(by, dict):
        by = {}

    by2: dict[str, list[int]] = {}
    for k, v in by.items():
        if not isinstance(v, list):
            continue
        cleaned: list[int] = []
        for x in v:
            try:
                cleaned.append(int(x))
            except Exception:
                continue
        by2[str(k)] = cleaned

    # Back-compat: seed email channel from legacy list
    by2.setdefault("email", list(st2))

    return EmailState(emailed_deliveries=ed2, sent_email_timestamps=st2, sent_timestamps_by_channel=by2)


def save_email_state(path: Path, state: EmailState) -> None:
    payload = {
        "emailed_deliveries": state.emailed_deliveries,
        "sent_email_timestamps": state.sent_email_timestamps,
        "sent_timestamps_by_channel": state.sent_timestamps_by_channel,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _prune_timestamps(ts: list[int]) -> list[int]:
    now = int(time.time())
    hour_ago = now - 3600
    return [t for t in ts if t >= hour_ago]


def prune_email_state(state: EmailState, retention_days: int = 14) -> None:
    now = int(time.time())
    cutoff = now - retention_days * 86400
    state.emailed_deliveries = {k: v for k, v in state.emailed_deliveries.items() if v >= cutoff}

    state.sent_email_timestamps = _prune_timestamps(state.sent_email_timestamps)
    for k, ts in list(state.sent_timestamps_by_channel.items()):
        state.sent_timestamps_by_channel[k] = _prune_timestamps(list(ts))


def can_send(state: EmailState, *, channel: str, max_per_hour: int) -> bool:
    prune_email_state(state)
    ts = state.sent_timestamps_by_channel.get(channel, [])
    return len(ts) < int(max_per_hour)


def mark_sent(state: EmailState, *, channel: str) -> None:
    ts = state.sent_timestamps_by_channel.setdefault(channel, [])
    ts.append(int(time.time()))

    # Back-compat: keep legacy list in sync for email
    if channel == "email":
        state.sent_email_timestamps = list(ts)


def can_send_email(state: EmailState, max_per_hour: int) -> bool:
    return can_send(state, channel="email", max_per_hour=max_per_hour)


def mark_email_sent(state: EmailState) -> None:
    mark_sent(state, channel="email")


def has_emailed_delivery(state: EmailState, delivery_number: str) -> bool:
    return str(delivery_number) in state.emailed_deliveries


def mark_delivery_emailed(state: EmailState, delivery_number: str) -> None:
    state.emailed_deliveries[str(delivery_number)] = int(time.time())