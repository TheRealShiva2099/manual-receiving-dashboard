from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from atc_email_state_store import (
    EmailState,
    can_send_email,
    has_emailed_delivery,
    load_email_state,
    mark_delivery_emailed,
    mark_email_sent,
    prune_email_state,
    save_email_state,
)
from atc_email_template import DeliveryEmailSummary, DeliveryItemLine, build_html, build_subject
from atc_roster_store import load_roster


def _safe_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _safe_str(x: Any) -> str:
    return str(x or "").strip()


def _group_delivery_events(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        d = _safe_str(e.get("delivery_number"))
        if not d:
            continue
        out[d].append(e)
    return dict(out)


def _build_delivery_summary(
    *,
    facility_id: str,
    delivery_number: str,
    events: list[dict[str, Any]],
) -> DeliveryEmailSummary:
    # Choose shift based on the first event.
    shift = _safe_str(events[0].get("shift_label")) or "Off Shift"

    # First detected: pick min rec_dt string (best-effort).
    rec_dts = sorted([_safe_str(e.get("rec_dt")) for e in events if _safe_str(e.get("rec_dt"))])
    first_detected = rec_dts[0] if rec_dts else time.strftime("%Y-%m-%d %H:%M:%S")

    loc_counts: dict[str, int] = defaultdict(int)
    for e in events:
        loc = _safe_str(e.get("location_id"))
        if loc:
            loc_counts[loc] += 1
    locations_sorted = [k for k, _ in sorted(loc_counts.items(), key=lambda kv: kv[1], reverse=True)]

    # Items aggregation
    by_item: dict[str, dict[str, Any]] = {}
    for e in events:
        item = _safe_str(e.get("item_nbr"))
        if not item:
            continue

        if item not in by_item:
            by_item[item] = {
                "vendor_name": _safe_str(e.get("vendor_name")),
                "cases": 0.0,
                "locs": set(),
            }

        by_item[item]["cases"] += _safe_float(e.get("case_qty"))
        loc = _safe_str(e.get("location_id"))
        if loc:
            by_item[item]["locs"].add(loc)

    item_lines: list[DeliveryItemLine] = []
    for item_nbr, meta in by_item.items():
        item_lines.append(
            DeliveryItemLine(
                item_nbr=item_nbr,
                vendor_name=str(meta.get("vendor_name") or ""),
                cases=float(meta.get("cases") or 0.0),
                locations=sorted(list(meta.get("locs") or [])),
            )
        )

    item_lines.sort(key=lambda x: x.cases, reverse=True)

    total_cases = sum(x.cases for x in item_lines)

    return DeliveryEmailSummary(
        facility_id=facility_id,
        shift_label=shift,
        delivery_number=delivery_number,
        first_detected_local=first_detected,
        locations=locations_sorted[:10],
        total_cases=total_cases,
        items=item_lines,
    )


def notify_new_deliveries(
    *,
    base_dir: Path,
    config: dict[str, Any],
    new_events: list[dict[str, Any]],
) -> None:
    """Create/send emails for new deliveries based on *new events*.

    In v2 while Graph admin consent is pending, we write HTML files to outbox.

    Guardrails:
    - one email per delivery_number
    - max emails per hour
    """

    email_cfg = config.get("email_notifications", {})
    enabled = bool(email_cfg.get("enabled", False))
    preview_outbox = bool(email_cfg.get("preview_outbox", True))

    if not enabled and not preview_outbox:
        return

    facility_id = str(config.get("monitoring", {}).get("facility_id", ""))

    roster = load_roster(base_dir / "atc_roster.json")

    state_path = base_dir / "atc_email_state.json"
    state: EmailState = load_email_state(state_path)
    prune_email_state(state)

    max_per_hour = int(email_cfg.get("max_emails_per_hour", 20))

    deliveries = _group_delivery_events(new_events)
    if not deliveries:
        return

    out_dir = base_dir / "outbox_emails"
    out_dir.mkdir(parents=True, exist_ok=True)

    for delivery_number, evs in deliveries.items():
        if has_emailed_delivery(state, delivery_number):
            continue

        summary = _build_delivery_summary(
            facility_id=facility_id,
            delivery_number=delivery_number,
            events=evs,
        )

        recipients = roster.inbound_recipients_for_shift(summary.shift_label)
        if not recipients:
            # No recipients for that shift -> do nothing (but don’t mark emailed).
            continue

        if not can_send_email(state, max_per_hour=max_per_hour):
            # Rate limited: stop processing to avoid spam.
            break

        subject = build_subject(summary)
        html = build_html(summary)

        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe_delivery = "".join(ch for ch in delivery_number if ch.isalnum() or ch in ("-", "_"))
        out_path = out_dir / f"delivery_{safe_delivery}_{stamp}.html"
        out_path.write_text(html, encoding="utf-8")

        # Save metadata sidecar
        meta_path = out_dir / f"delivery_{safe_delivery}_{stamp}.json"
        meta_path.write_text(
            json.dumps(
                {
                    "delivery_number": delivery_number,
                    "shift_label": summary.shift_label,
                    "recipients": recipients,
                    "subject": subject,
                    "summary": asdict(summary),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        # Mark as "sent" (outbox counts as sent for dedupe/rate limiting)
        mark_email_sent(state)
        mark_delivery_emailed(state, delivery_number)

    save_email_state(state_path, state)
