from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SHIFTS = ("Shift A1", "Shift A2", "Shift B1", "Off Shift")


@dataclass(frozen=True)
class Roster:
    inbound_by_shift: dict[str, list[str]]

    def inbound_recipients_for_shift(self, shift_label: str) -> list[str]:
        shift_label = str(shift_label or "Off Shift")
        return list(self.inbound_by_shift.get(shift_label, []))


def load_roster(path: Path) -> Roster:
    """Load roster JSON.

    Schema is inbound-only.
    """

    if not path.exists():
        return Roster(inbound_by_shift={s: [] for s in SHIFTS})

    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return Roster(inbound_by_shift={s: [] for s in SHIFTS})

    roles = payload.get("roles", {}) if isinstance(payload, dict) else {}
    inbound = roles.get("inbound", {}) if isinstance(roles, dict) else {}

    inbound_by_shift: dict[str, list[str]] = {s: [] for s in SHIFTS}
    for s in SHIFTS:
        raw = inbound.get(s, [])
        if not isinstance(raw, list):
            continue
        cleaned = sorted({str(x).strip().lower() for x in raw if str(x).strip() and "@" in str(x)})
        inbound_by_shift[s] = cleaned

    return Roster(inbound_by_shift=inbound_by_shift)
