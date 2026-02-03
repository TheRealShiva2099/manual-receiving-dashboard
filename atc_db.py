from __future__ import annotations

import csv
import io
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DB_FILENAME = "atc.db"


@dataclass(frozen=True)
class DbPaths:
    base_dir: Path

    @property
    def db_path(self) -> Path:
        return self.base_dir / DB_FILENAME

    @property
    def legacy_triage_json(self) -> Path:
        return self.base_dir / "atc_delivery_triage.json"


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def init_db(base_dir: Path) -> None:
    paths = DbPaths(base_dir=base_dir)
    with _connect(paths.db_path) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS delivery_state (
              delivery_number TEXT PRIMARY KEY,

              -- floor triage
              checked INTEGER NOT NULL DEFAULT 0,
              primary_cause TEXT NOT NULL DEFAULT '',
              escalation TEXT NOT NULL DEFAULT '',
              note TEXT NOT NULL DEFAULT '',

              -- QA
              qa_status TEXT NOT NULL DEFAULT '',
              qa_note TEXT NOT NULL DEFAULT '',

              -- audit (QA/DC check-up)
              audit_completed INTEGER NOT NULL DEFAULT 0,
              audit_completed_at_epoch INTEGER NOT NULL DEFAULT 0,
              audit_completed_by TEXT NOT NULL DEFAULT '',

              -- lifecycle/visibility (hide from active when no cases left)
              cleared_from_active INTEGER NOT NULL DEFAULT 0,
              cleared_reason TEXT NOT NULL DEFAULT '',
              cleared_at_epoch INTEGER NOT NULL DEFAULT 0,
              cleared_by TEXT NOT NULL DEFAULT '',

              updated_at_epoch INTEGER NOT NULL DEFAULT 0,
              updated_by TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_delivery_state_updated_at
              ON delivery_state(updated_at_epoch);

            CREATE TABLE IF NOT EXISTS delivery_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              delivery_number TEXT NOT NULL,
              event_type TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at_epoch INTEGER NOT NULL,
              created_by TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_delivery_events_delivery
              ON delivery_events(delivery_number);
            """
        )


def _coerce_bool(value: Any) -> int:
    return 1 if bool(value) else 0


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def migrate_from_legacy_triage_json_if_needed(base_dir: Path) -> None:
    """One-time migration:

    - If DB is empty and legacy triage JSON exists, import it.
    - We intentionally do NOT delete the legacy JSON.

    Safe: idempotent-ish, only runs when delivery_state is empty.
    """

    init_db(base_dir)
    paths = DbPaths(base_dir=base_dir)

    if not paths.legacy_triage_json.exists():
        return

    with _connect(paths.db_path) as con:
        row = con.execute("SELECT COUNT(*) AS c FROM delivery_state").fetchone()
        if row and int(row["c"] or 0) > 0:
            return

        try:
            payload = json.loads(paths.legacy_triage_json.read_text(encoding="utf-8"))
        except Exception:
            return

        deliveries = payload.get("deliveries", {}) if isinstance(payload, dict) else {}
        if not isinstance(deliveries, dict):
            return

        now = int(time.time())
        for delivery_number, triage in deliveries.items():
            if not isinstance(triage, dict):
                continue
            dn = _coerce_str(delivery_number)
            if not dn:
                continue

            updates = {
                "checked": _coerce_bool(triage.get("checked", False)),
                "primary_cause": _coerce_str(triage.get("primary_cause", "")),
                "escalation": _coerce_str(triage.get("escalation", "")),
                "note": _coerce_str(triage.get("note", "")),
                "qa_status": _coerce_str(triage.get("qa_status", "")),
                "qa_note": _coerce_str(triage.get("qa_note", "")),
                "updated_at_epoch": _coerce_int(triage.get("updated_at_epoch") or now),
                "updated_by": _coerce_str(triage.get("updated_by", "")),
            }

            _upsert_state(con, dn, updates)

        con.commit()


def get_delivery_state(base_dir: Path, delivery_number: str) -> dict[str, Any] | None:
    init_db(base_dir)
    paths = DbPaths(base_dir=base_dir)

    dn = _coerce_str(delivery_number)
    if not dn:
        return None

    with _connect(paths.db_path) as con:
        row = con.execute(
            "SELECT * FROM delivery_state WHERE delivery_number = ?",
            (dn,),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def upsert_delivery_state(
    base_dir: Path,
    *,
    delivery_number: str,
    updates: dict[str, Any],
    event_type: str,
) -> dict[str, Any]:
    """Upsert delivery state and append an event row."""

    init_db(base_dir)
    paths = DbPaths(base_dir=base_dir)

    dn = _coerce_str(delivery_number)
    if not dn:
        raise ValueError("delivery_number is required")

    now = int(time.time())
    clean: dict[str, Any] = {}

    allowed: dict[str, str] = {
        # floor triage
        "checked": "int",
        "primary_cause": "str",
        "escalation": "str",
        "note": "str",

        # QA
        "qa_status": "str",
        "qa_note": "str",

        # audit
        "audit_completed": "int",
        "audit_completed_at_epoch": "int",
        "audit_completed_by": "str",

        # clear
        "cleared_from_active": "int",
        "cleared_reason": "str",
        "cleared_at_epoch": "int",
        "cleared_by": "str",

        # generic
        "updated_at_epoch": "int",
        "updated_by": "str",
    }

    for k, v in (updates or {}).items():
        if k not in allowed:
            continue
        t = allowed[k]
        if t == "int":
            if k in {"checked", "audit_completed", "cleared_from_active"}:
                clean[k] = _coerce_bool(v)
            else:
                clean[k] = _coerce_int(v)
        else:
            clean[k] = _coerce_str(v)

    # always touch updated_at
    clean.setdefault("updated_at_epoch", now)

    with _connect(paths.db_path) as con:
        _upsert_state(con, dn, clean)
        con.execute(
            """
            INSERT INTO delivery_events(delivery_number, event_type, payload_json, created_at_epoch, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                dn,
                _coerce_str(event_type) or "update",
                json.dumps(clean, sort_keys=True),
                now,
                _coerce_str(clean.get("updated_by", "")),
            ),
        )
        con.commit()

        row = con.execute(
            "SELECT * FROM delivery_state WHERE delivery_number = ?",
            (dn,),
        ).fetchone()
        return dict(row) if row else {"delivery_number": dn, **clean}


def _upsert_state(con: sqlite3.Connection, delivery_number: str, updates: dict[str, Any]) -> None:
    cols = ["delivery_number"] + sorted(updates.keys())
    placeholders = ["?"] * len(cols)
    update_set = ", ".join([f"{c}=excluded.{c}" for c in cols if c != "delivery_number"])

    values = [delivery_number] + [updates[c] for c in cols if c != "delivery_number"]

    sql = (
        f"INSERT INTO delivery_state({', '.join(cols)}) VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT(delivery_number) DO UPDATE SET {update_set}"
    )
    con.execute(sql, values)


def export_delivery_state_rows(base_dir: Path) -> Iterable[dict[str, Any]]:
    init_db(base_dir)
    paths = DbPaths(base_dir=base_dir)
    with _connect(paths.db_path) as con:
        rows = con.execute("SELECT * FROM delivery_state").fetchall()
        for r in rows:
            yield dict(r)


def export_delivery_state_csv(base_dir: Path) -> str:
    rows = list(export_delivery_state_rows(base_dir))
    if not rows:
        return ""

    fieldnames = sorted({k for r in rows for k in r.keys()})
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()
