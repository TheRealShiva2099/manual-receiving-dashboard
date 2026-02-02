"""Validate shift label correctness for Deliveries page vs notification-time reality.

Hypothesis:
- Deliveries page currently uses the most-common shift_label across *all* events
  for a delivery within retention.
- Teams notification shift is effectively based on what shift label was present
  when the delivery first hit the notify threshold.

This script compares:
1) shift_mode_all: mode of shift_label across all events for delivery
2) shift_mode_near_notify: mode of shift_label across events within a window
   around notified_at timestamp.

Run:
  python debug_shift_validation.py

Optional:
  python debug_shift_validation.py --window-minutes 90 --limit 50
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _parse_detected_at(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _mode(values: list[str]) -> str:
    c = Counter([v for v in values if v])
    if not c:
        return ""
    return c.most_common(1)[0][0]


@dataclass(frozen=True)
class DeliveryShiftStats:
    delivery: str
    notified_at: datetime | None
    shift_mode_all: str
    shift_counts_all: dict[str, int]
    shift_mode_near_notify: str
    shift_counts_near_notify: dict[str, int]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-minutes", type=int, default=90)
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    events_log = _load_json(BASE_DIR / "atc_events_log.json")
    email_state = _load_json(BASE_DIR / "atc_email_state.json")

    notified_map = email_state.get("emailed_deliveries", {})
    if not isinstance(notified_map, dict):
        notified_map = {}

    events = events_log.get("events", [])
    if not isinstance(events, list):
        events = []

    # Group events by delivery
    by_delivery: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        if not isinstance(e, dict):
            continue
        d = _norm(e.get("delivery_number"))
        if not d:
            continue
        by_delivery.setdefault(d, []).append(e)

    window = timedelta(minutes=int(args.window_minutes))

    stats: list[DeliveryShiftStats] = []
    for delivery, evs in by_delivery.items():
        if delivery not in notified_map:
            continue

        # notified_at is epoch seconds in emailed_deliveries
        try:
            notified_epoch = int(notified_map[delivery])
            notified_at = datetime.fromtimestamp(notified_epoch)
        except Exception:
            notified_at = None

        shifts_all = [_norm(e.get("shift_label")) for e in evs if _norm(e.get("shift_label"))]
        shift_mode_all = _mode(shifts_all)
        counts_all = dict(Counter(shifts_all))

        shifts_near: list[str] = []
        if notified_at is not None:
            lo = notified_at - window
            hi = notified_at + window
            for e in evs:
                dt = _parse_detected_at(_norm(e.get("detected_at")))
                if dt is None:
                    continue
                if lo <= dt <= hi:
                    shifts_near.append(_norm(e.get("shift_label")))

        shift_mode_near = _mode(shifts_near) if shifts_near else ""
        counts_near = dict(Counter([s for s in shifts_near if s]))

        stats.append(
            DeliveryShiftStats(
                delivery=delivery,
                notified_at=notified_at,
                shift_mode_all=shift_mode_all,
                shift_counts_all=counts_all,
                shift_mode_near_notify=shift_mode_near,
                shift_counts_near_notify=counts_near,
            )
        )

    mismatches = [
        s
        for s in stats
        if s.shift_mode_near_notify
        and s.shift_mode_all
        and s.shift_mode_near_notify != s.shift_mode_all
    ]

    # Sort by notified_at newest first
    mismatches.sort(key=lambda s: s.notified_at or datetime.min, reverse=True)

    print("=== Shift Validation Report ===")
    print("window_minutes:", args.window_minutes)
    print("notified_deliveries_total:", len(stats))
    print("mismatches:", len(mismatches))

    for s in mismatches[: int(args.limit)]:
        print("\nDelivery", s.delivery)
        print("  notified_at:", s.notified_at)
        print("  shift_mode_all:", s.shift_mode_all, s.shift_counts_all)
        print("  shift_mode_near_notify:", s.shift_mode_near_notify, s.shift_counts_near_notify)

    if len(mismatches) > int(args.limit):
        print(f"\n... ({len(mismatches) - int(args.limit)} more mismatches)")

    # Also show deliveries that have multiple shifts but no near-notify info
    multi_shift = [s for s in stats if len([k for k in s.shift_counts_all.keys() if k]) > 1]
    multi_shift.sort(key=lambda s: sum(s.shift_counts_all.values()), reverse=True)

    print("\n=== Multi-shift deliveries (all-events) ===")
    for s in multi_shift[:10]:
        print("Delivery", s.delivery, "counts=", s.shift_counts_all, "notified_at=", s.notified_at)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
