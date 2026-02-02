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

    # delivery_number -> shift_label at time of notification (anchors Deliveries page)
    notified_shift_by_delivery: dict[str, str]

    # delivery_number -> cumulative manual cases observed (used for thresholding)
    delivery_case_totals: dict[str, float]

    # delivery_number -> last seen epoch seconds (for pruning threshold state)
    delivery_case_last_seen: dict[str, int]

    # Legacy: timestamps of sent emails (epoch seconds) for rate limiting
    sent_email_timestamps: list[int]

    # New: rate-limiting buckets per channel (email/teams/etc)
    sent_timestamps_by_channel: dict[str, list[int]]


def load_email_state(path: Path) -> EmailState:
    if not path.exists():
        return EmailState(
            emailed_deliveries={},
            notified_shift_by_delivery={},
            delivery_case_totals={},
            delivery_case_last_seen={},
            sent_email_timestamps=[],
            sent_timestamps_by_channel={},
        )

    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return EmailState(
            emailed_deliveries={},
            notified_shift_by_delivery={},
            delivery_case_totals={},
            delivery_case_last_seen={},
            sent_email_timestamps=[],
            sent_timestamps_by_channel={},
        )

    ed = payload.get("emailed_deliveries", {})
    ns = payload.get("notified_shift_by_delivery", {})
    ct = payload.get("delivery_case_totals", {})
    ls = payload.get("delivery_case_last_seen", {})
    st = payload.get("sent_email_timestamps", [])

    if not isinstance(ed, dict):
        ed = {}
    if not isinstance(ns, dict):
        ns = {}
    if not isinstance(ct, dict):
        ct = {}
    if not isinstance(ls, dict):
        ls = {}
    if not isinstance(st, list):
        st = []

    ed2: dict[str, int] = {}
    for k, v in ed.items():
        try:
            ed2[str(k)] = int(v)
        except Exception:
            continue

    ns2: dict[str, str] = {}
    for k, v in ns.items():
        s = str(v or "").strip()
        if s:
            ns2[str(k)] = s

    ct2: dict[str, float] = {}
    for k, v in ct.items():
        try:
            ct2[str(k)] = float(v)
        except Exception:
            continue

    ls2: dict[str, int] = {}
    for k, v in ls.items():
        try:
            ls2[str(k)] = int(v)
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

    return EmailState(
        emailed_deliveries=ed2,
        notified_shift_by_delivery=ns2,
        delivery_case_totals=ct2,
        delivery_case_last_seen=ls2,
        sent_email_timestamps=st2,
        sent_timestamps_by_channel=by2,
    )


def save_email_state(path: Path, state: EmailState) -> None:
    payload = {
        "emailed_deliveries": state.emailed_deliveries,
        "notified_shift_by_delivery": state.notified_shift_by_delivery,
        "delivery_case_totals": state.delivery_case_totals,
        "delivery_case_last_seen": state.delivery_case_last_seen,
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

    # Keep only recently-notified deliveries.
    state.emailed_deliveries = {k: v for k, v in state.emailed_deliveries.items() if v >= cutoff}

    # Keep anchored shift labels only for deliveries we still track.
    state.notified_shift_by_delivery = {
        k: str(v)
        for k, v in state.notified_shift_by_delivery.items()
        if k in state.emailed_deliveries
    }

    # Prune threshold tracking.
    state.delivery_case_last_seen = {
        k: int(v) for k, v in state.delivery_case_last_seen.items() if int(v) >= cutoff
    }
    state.delivery_case_totals = {
        k: float(v)
        for k, v in state.delivery_case_totals.items()
        if (k in state.delivery_case_last_seen) or (k in state.emailed_deliveries)
    }

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


def mark_delivery_emailed(state: EmailState, delivery_number: str, *, shift_label: str | None = None) -> None:
    key = str(delivery_number)
    state.emailed_deliveries[key] = int(time.time())
    if shift_label:
        state.notified_shift_by_delivery[key] = str(shift_label).strip()


def get_delivery_case_total(state: EmailState, delivery_number: str) -> float:
    return float(state.delivery_case_totals.get(str(delivery_number), 0.0))


def record_delivery_cases(state: EmailState, *, delivery_number: str, added_cases: float) -> float:
    """Accumulate manual cases for a delivery and return the new total."""

    key = str(delivery_number)
    total = float(state.delivery_case_totals.get(key, 0.0)) + float(added_cases or 0.0)
    state.delivery_case_totals[key] = total
    state.delivery_case_last_seen[key] = int(time.time())
    return total
