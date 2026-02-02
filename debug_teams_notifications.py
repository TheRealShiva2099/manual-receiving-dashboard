"""Debug Teams webhook notification silence.

Goal: quickly answer:
- Is ATC detecting new deliveries?
- Are those deliveries being deduped as already notified?
- When was the last *recorded* Teams send?

This script is read-only.

Run:
  python debug_teams_notifications.py

Optional:
  python debug_teams_notifications.py --since-hours 4
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class DebugResult:
    last_teams_sent: datetime | None
    last_outbox_mtime: datetime | None
    latest_detected_at: datetime | None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_dt(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        # expected: 2026-01-29T10:26:46
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _latest_outbox_mtime(outbox: Path) -> datetime | None:
    if not outbox.exists():
        return None
    files = [p for p in outbox.glob("*") if p.is_file()]
    if not files:
        return None
    newest = max(files, key=lambda p: p.stat().st_mtime)
    return datetime.fromtimestamp(newest.stat().st_mtime)


def _last_teams_sent(email_state: dict[str, Any]) -> datetime | None:
    ts = (email_state.get("sent_timestamps_by_channel", {}) or {}).get("teams", []) or []
    if not ts:
        return None
    # Stored as epoch seconds
    return datetime.fromtimestamp(max(ts))


def _latest_detected_at(events_log: dict[str, Any]) -> datetime | None:
    events = events_log.get("events", []) or []
    dts = [_parse_dt(e.get("detected_at", "")) for e in events]
    dts = [d for d in dts if d is not None]
    return max(dts) if dts else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-hours", type=float, default=None)
    args = ap.parse_args()

    events_log = _load_json(BASE_DIR / "atc_events_log.json")
    email_state = _load_json(BASE_DIR / "atc_email_state.json")

    emailed_deliveries: set[str] = set((email_state.get("emailed_deliveries", {}) or {}).keys())

    last_teams = _last_teams_sent(email_state)
    last_outbox = _latest_outbox_mtime(BASE_DIR / "outbox_emails")
    latest_detected = _latest_detected_at(events_log)

    print("=== ATC Teams Notification Debug ===")
    print("Now:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("Last teams sent:", last_teams)
    print("Last outbox write:", last_outbox)
    print("Latest detected_at in log:", latest_detected)

    since = None
    if args.since_hours is not None:
        since = datetime.now() - timedelta(hours=float(args.since_hours))
    elif last_teams is not None:
        since = last_teams

    if since is None:
        print("No cutoff time available (no last teams sent, and --since-hours not provided).")
        return 0

    events = events_log.get("events", []) or []
    after = []
    for e in events:
        dt = _parse_dt(e.get("detected_at", ""))
        if dt is None or dt <= since:
            continue
        after.append(e)

    deliveries = sorted({str(e.get("delivery_number", "")).strip() for e in after if str(e.get("delivery_number", "")).strip()})

    print("\nCutoff:", since)
    print("Events after cutoff:", len(after))
    print("Distinct deliveries after cutoff:", len(deliveries))

    # Aggregate per delivery so we can spot rec_dt lag vs detected_at.
    by_delivery: dict[str, list[dict[str, Any]]] = {}
    for e in after:
        d = str(e.get("delivery_number", "")).strip()
        if not d:
            continue
        by_delivery.setdefault(d, []).append(e)

    def parse_rec_dt(s: str) -> datetime | None:
        s = (s or "").strip()
        if not s:
            return None
        # BigQuery DATETIME-ish, often with fractional seconds.
        try:
            return datetime.fromisoformat(s.replace(" ", "T"))
        except Exception:
            if "." in s:
                base = s.split(".", 1)[0]
                try:
                    return datetime.fromisoformat(base.replace(" ", "T"))
                except Exception:
                    return None
            return None

    for d in deliveries[:25]:
        evs = by_delivery.get(d, [])
        shifts = sorted({str(x.get("shift_label", "")).strip() for x in evs if str(x.get("shift_label", "")).strip()})
        rec_dts = [parse_rec_dt(str(x.get("rec_dt", ""))) for x in evs]
        rec_dts = [x for x in rec_dts if x is not None]
        det_dts = [_parse_dt(str(x.get("detected_at", ""))) for x in evs]
        det_dts = [x for x in det_dts if x is not None]
        rec_range = (min(rec_dts), max(rec_dts)) if rec_dts else (None, None)
        det_range = (min(det_dts), max(det_dts)) if det_dts else (None, None)

        print(
            "-",
            d,
            "deduped=",
            (d in emailed_deliveries),
            "shift=",
            ",".join(shifts) if shifts else "-",
            "rec_dt=",
            rec_range[0],
            "..",
            rec_range[1],
            "detected_at=",
            det_range[0],
            "..",
            det_range[1],
        )

    if len(deliveries) > 25:
        print(f"... ({len(deliveries) - 25} more)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
