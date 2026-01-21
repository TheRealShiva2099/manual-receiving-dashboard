"""Manual Receiving ATC (US-07377)

Westly-style architecture:
- Poll BigQuery on an interval (via `bq` CLI)
- Detect NEW manual receiving events using a persisted state file
- Send Windows toast notifications (plyer)
- Persist last-24h events into a JSON event log
- Generate a static HTML dashboard file for a tiny Flask server to serve

Notes:
- We intentionally use `bq` CLI (not the Python SDK). Less auth drama.
- Keep files small and readable. If this grows, we split it.

Run (debug):
  python manual_receiving_atc.py

Run (silent):
  start_atc_hidden.vbs (via the provided batch file)
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from plyer import notification

from atc_delivery_notifications import notify_new_deliveries


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "atc_config.json"
STATE_PATH = BASE_DIR / "atc_state.json"
EVENTS_LOG_PATH = BASE_DIR / "atc_events_log.json"
STATUS_PATH = BASE_DIR / "atc_status.json"
DASHBOARD_PATH = BASE_DIR / "atc_dashboard.html"
TEMPLATE_PATH = BASE_DIR / "dashboard_template.html"
ANALYTICS_PATH = BASE_DIR / "atc_analytics.html"
ANALYTICS_TEMPLATE_PATH = BASE_DIR / "analytics_template.html"
VIZ_PATH = BASE_DIR / "atc_viz.html"
VIZ_TEMPLATE_PATH = BASE_DIR / "viz_template.html"
ROSTER_PATH = BASE_DIR / "atc_roster.html"
ROSTER_TEMPLATE_PATH = BASE_DIR / "roster_template.html"
LAST_QUERY_PATH = BASE_DIR / "last_atc_query.sql"


@dataclass(frozen=True)
class AtcEvent:
    rec_dt: str
    location_id: str
    container_id: str
    item_nbr: str
    vendor_name: str
    delivery_number: str
    shift_label: str
    case_qty: float

    def event_id(self) -> str:
        # Site decision: container_id is the unique identifier for a case.
        # So dedupe/identity is container-level.
        return self.container_id


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Missing config: {CONFIG_PATH}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in {CONFIG_PATH}: {e}")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"last_check": None, "seen_event_ids": []}

    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"last_check": None, "seen_event_ids": []}

    if not isinstance(payload, dict):
        return {"last_check": None, "seen_event_ids": []}

    seen = payload.get("seen_event_ids")
    if not isinstance(seen, list):
        seen = []

    return {"last_check": payload.get("last_check"), "seen_event_ids": seen}


def save_state(seen_event_ids: list[str]) -> None:
    # Prune so the file doesn’t grow forever.
    pruned = seen_event_ids[-5000:]
    payload = {"last_check": _now_iso(), "seen_event_ids": pruned}
    STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_events_log() -> dict[str, Any]:
    if not EVENTS_LOG_PATH.exists():
        return {"events": []}

    try:
        payload = json.loads(EVENTS_LOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"events": []}

    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        return {"events": []}

    return payload


def save_events_log(events: list[dict[str, Any]]) -> None:
    EVENTS_LOG_PATH.write_text(json.dumps({"events": events}, indent=2), encoding="utf-8")


def _bq_query_sql(config: dict[str, Any]) -> str:
    """Build the ATC polling query.

    Design priorities:
    - FAST enough to run repeatedly (not 80GB / 5 minutes… gross)
    - Use your site’s manual receiving definition + overflow locations
    - Return event-level rows for alerting

    Performance tricks we apply:
    - Filter BOTH source tables by time window before joining
    - Reduce RECEIVING_ITEM to the *latest row per container* in the window
    - Make expensive vendor name join optional
    """

    facility_id = config["monitoring"]["facility_id"]
    tz = config["monitoring"].get("timezone", "America/New_York")
    overflow_locations: list[str] = config["monitoring"].get("overflow_locations", [])
    query_window_minutes = int(config.get("monitoring", {}).get("query_window_minutes", 60))

    include_vendor = bool(config.get("bigquery", {}).get("include_vendor_name", False))

    # Overflow/exempt locations should not appear in the dashboard/alerts.
    overflow_filter = ""
    if overflow_locations:
        quoted = ", ".join([f"'{x}'" for x in overflow_locations])
        overflow_filter = f"\n      AND r.LOCATION_ID NOT IN ({quoted})"

    vendor_select = "'' AS vendor_name"
    vendor_joins = ""
    if include_vendor:
        vendor_select = "CAST(o.VNDR_NAME AS STRING) AS vendor_name"
        vendor_joins = """
LEFT JOIN `wmt-edw-prod.US_SUPPLY_CHAIN_SCT_NONCAT_VM.DELIVERY_DOC` d
  ON c.DELIVERY_NUMBER = d.DELIVERY_NUMBER
LEFT JOIN `wmt-cp-prod.TRANS.ICC_ORD_SCH` o
  ON d.OMS_PO_NBR = CAST(o.OMS_PO_NBR AS STRING)
""".rstrip()

    # NOTE: We assume c.CONTAINER_CREATE_TS and r.ENTITY_OPERATION_TS are partition-friendly.
    # This is “Westly-style” output columns, but optimized:
    # - filter by window before join
    # - pick latest receiving row per container to avoid duplicates
    return f"""
WITH
  r_filtered AS (
    -- Manual receiving events (event-time based on ENTITY_OPERATION_TS)
    SELECT
      r.CONTAINER_ID,
      r.LOCATION_ID,
      r.MESSAGE_ID,
      r.RCV_SET_ON_CONVEYOR_IND,
      SAFE_DIVIDE(r.ITEM_QTY, NULLIF(r.VNPK_QTY, 0)) AS CASE_QTY,
      r.ENTITY_OPERATION_TS
    FROM `wmt-edw-prod.US_SUPPLY_CHAIN_SCT_NONCAT_VM.RECEIVING_ITEM` r
    WHERE r.FACILITY = '{facility_id}'
      AND r.ENTITY_OPERATION_TS >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {query_window_minutes} MINUTE)
      AND r.RCV_SET_ON_CONVEYOR_IND = TRUE{overflow_filter}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY r.CONTAINER_ID ORDER BY r.ENTITY_OPERATION_TS DESC) = 1
  ),
  c_filtered AS (
    -- 1 row per container, but only for containers that appear in r_filtered.
    SELECT
      c.CONTAINER_ID,
      ANY_VALUE(c.ITEM_NBR) AS ITEM_NBR,
      ANY_VALUE(c.DELIVERY_NUMBER) AS DELIVERY_NUMBER
    FROM `wmt-edw-prod.US_SUPPLY_CHAIN_SCT_NONCAT_VM.CONTAINER_ITEM_OPERATIONS` c
    WHERE c.FACILITY = '{facility_id}'
      AND c.CONTAINER_ID IN (SELECT CONTAINER_ID FROM r_filtered)
    GROUP BY c.CONTAINER_ID
  )

SELECT
  CAST(DATETIME(r.ENTITY_OPERATION_TS, '{tz}') AS STRING) AS rec_dt,
  CAST(r.LOCATION_ID AS STRING) AS location_id,
  CAST(c.CONTAINER_ID AS STRING) AS container_id,
  CAST(c.ITEM_NBR AS STRING) AS item_nbr,
  {vendor_select},
  CAST(c.DELIVERY_NUMBER AS STRING) AS delivery_number,

  CAST(r.CASE_QTY AS STRING) AS case_qty,

  CASE
    WHEN EXTRACT(DAYOFWEEK FROM DATETIME(r.ENTITY_OPERATION_TS, '{tz}')) IN (3,4,5,6)
     AND EXTRACT(TIME FROM DATETIME(r.ENTITY_OPERATION_TS, '{tz}')) BETWEEN '04:30:00' AND '15:30:00'
    THEN 'Shift A1'

    WHEN EXTRACT(DAYOFWEEK FROM DATETIME(r.ENTITY_OPERATION_TS, '{tz}')) IN (3,4,5,6)
     AND (
       EXTRACT(TIME FROM DATETIME(r.ENTITY_OPERATION_TS, '{tz}')) BETWEEN '15:30:00' AND '23:59:59'
       OR EXTRACT(TIME FROM DATETIME(r.ENTITY_OPERATION_TS, '{tz}')) BETWEEN '00:00:00' AND '02:00:00'
     )
    THEN 'Shift A2'

    WHEN EXTRACT(DAYOFWEEK FROM DATETIME(r.ENTITY_OPERATION_TS, '{tz}')) IN (1,2,7)
     AND EXTRACT(TIME FROM DATETIME(r.ENTITY_OPERATION_TS, '{tz}')) BETWEEN '04:30:00' AND '18:00:00'
    THEN 'Shift B1'

    ELSE 'Off Shift'
  END AS shift_label

FROM c_filtered c
JOIN r_filtered r
  ON c.CONTAINER_ID = r.CONTAINER_ID
{vendor_joins}

WHERE c.CONTAINER_ID <> r.MESSAGE_ID

ORDER BY r.ENTITY_OPERATION_TS DESC
LIMIT 2000
""".strip()


def _resolve_bq_exe(config: dict[str, Any]) -> str:
    # 1) Config override
    bq_path = str(config.get("bigquery", {}).get("bq_path", "")).strip()
    if bq_path:
        # If configured, always use it. Don’t “helpfully” fall back to some other bq.
        p = Path(bq_path)
        if not p.exists():
            raise FileNotFoundError(
                f"Configured bq_path does not exist: {bq_path}\n"
                "Fix atc_config.json bigquery.bq_path to the result of: where bq"
            )
        return str(p)

    # 2) PATH
    which = shutil.which("bq")
    if which:
        return which

    # 3) Common Windows install locations (best-effort)
    candidates = [
        Path("C:/Program Files (x86)/Google/Cloud SDK/google-cloud-sdk/bin/bq.cmd"),
        Path("C:/Program Files/Google/Cloud SDK/google-cloud-sdk/bin/bq.cmd"),
        Path.home() / "AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/bq.cmd",
        Path.home() / "AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/bq.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    raise FileNotFoundError(
        "BigQuery CLI 'bq' was not found.\n"
        "Fix: install Google Cloud SDK AND ensure bq is on PATH, or set bigquery.bq_path in atc_config.json.\n"
        "Tip: open a Command Prompt and run: where bq"
    )


def _resolve_bq_argv(bq_path: str) -> list[str]:
    """Return argv to invoke BigQuery CLI reliably.

    On Windows, `bq.cmd` runs Cloud SDK’s python + `bin/bootstrapping/bq.py`.
    We call that directly to avoid cmd.exe quoting issues.
    """

    p = Path(bq_path)
    if p.suffix.lower() in {".cmd", ".bat"}:
        cloudsdk_root = p.parent.parent  # .../google-cloud-sdk
        bq_py = cloudsdk_root / "bin" / "bootstrapping" / "bq.py"
        bundled_python = cloudsdk_root / "platform" / "bundledpython" / "python.exe"

        python_exe = str(bundled_python) if bundled_python.exists() else sys.executable
        if not bq_py.exists():
            raise FileNotFoundError(f"Cloud SDK bq.py not found: {bq_py}")

        return [python_exe, str(bq_py)]

    return [bq_path]


def _run_bq_query(config: dict[str, Any], sql: str, billing_project: str | None) -> str:
    """Run BigQuery via bq CLI.

    Important Windows detail:
    - Passing a big SQL string as a command-line arg can hit the ~8191 char limit.
    - So we pipe the SQL via STDIN instead.
    """

    bq_exe = _resolve_bq_exe(config)
    # Persist the last query for debugging/review.
    try:
        LAST_QUERY_PATH.write_text(sql + "\n", encoding="utf-8")
    except OSError:
        pass

    print(f"[INFO] Using bq: {bq_exe}", flush=True)

    base_args = [
        "query",
        "--quiet",
        "--use_legacy_sql=false",
        "--format=csv",
    ]
    if billing_project:
        base_args.append(f"--project_id={billing_project}")

    cmd = _resolve_bq_argv(bq_exe) + base_args

    try:
        completed = subprocess.run(
            cmd,
            input=sql,
            capture_output=True,
            text=True,
            check=False,
            timeout=int(config.get("monitoring", {}).get("bq_timeout_seconds", 600)),
            shell=False,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            "bq query timed out.\n"
            "This usually means the query is scanning too much data or BigQuery is slow.\n"
            "Try reducing monitoring.query_window_minutes in atc_config.json (ex: 60).\n"
            f"Details: {e}"
        )

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        details = stderr or stdout or "(no output from bq)"
        raise RuntimeError(f"bq query failed (exit={completed.returncode}):\n{details}")

    return completed.stdout


def _parse_events_csv(csv_text: str) -> list[AtcEvent]:
    # bq CSV format includes header row.
    reader = csv.DictReader(csv_text.splitlines())
    events: list[AtcEvent] = []

    for row in reader:
        # Defensive defaults. BQ sometimes returns "NULL" strings.
        def get(name: str) -> str:
            val = (row.get(name) or "").strip()
            return "" if val.upper() == "NULL" else val

        def get_float(name: str) -> float:
            s = get(name)
            try:
                return float(s) if s else 0.0
            except ValueError:
                return 0.0

        event = AtcEvent(
            rec_dt=get("rec_dt"),
            location_id=get("location_id"),
            container_id=get("container_id"),
            item_nbr=get("item_nbr"),
            vendor_name=get("vendor_name"),
            delivery_number=get("delivery_number"),
            shift_label=get("shift_label"),
            case_qty=get_float("case_qty"),
        )

        # Minimal sanity: ignore blank container ids.
        if not event.container_id:
            continue

        events.append(event)

    return events


def _filter_recent(events: Iterable[AtcEvent], lookback_minutes: int) -> list[AtcEvent]:
    # rec_dt is a string like "YYYY-MM-DD HH:MM:SS". Parse best-effort.
    cutoff = datetime.now() - timedelta(minutes=lookback_minutes)

    def parse_dt(s: str) -> datetime | None:
        s = (s or "").strip()
        if not s:
            return None

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                pass

        if "." in s:
            base = s.split(".", 1)[0]
            try:
                return datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None

    out: list[AtcEvent] = []
    for e in events:
        dt = parse_dt(e.rec_dt)
        if dt is None:
            continue
        if dt >= cutoff:
            out.append(e)
    return out


def _send_notification(config: dict[str, Any], event: AtcEvent) -> None:
    app_name = config.get("notifications", {}).get("app_name", "Manual Receiving ATC")
    timeout = int(config.get("notifications", {}).get("duration_seconds", 600))

    title = "[ALERT] Manual Receiving Event"
    message = (
        f"Facility: {config['monitoring']['facility_id']}\n"
        f"Location: {event.location_id}\n"
        f"Vendor: {event.vendor_name}\n"
        f"Item: {event.item_nbr}\n"
        f"Container: {event.container_id}\n"
        f"Delivery: {event.delivery_number}\n"
        f"Shift: {event.shift_label}\n"
        f"Time: {event.rec_dt}"
    )

    notification.notify(
        title=title,
        message=message,
        app_name=app_name,
        timeout=timeout,
    )


def _event_key_from_dict(d: dict[str, Any]) -> str:
    # Must match AtcEvent.event_id() composition.
    return str(d.get("container_id", ""))


def upsert_events_to_log(events: list[AtcEvent], config: dict[str, Any]) -> None:
    """Persist events for the dashboard.

    Important behavior:
    - We keep a rolling local event log for the dashboard/viz pages.
    - Retention window is controlled by config.monitoring.event_log_retention_days.

    We still keep notifications based on `new_events` separately.
    """

    payload = load_events_log()
    existing: list[dict[str, Any]] = payload.get("events", [])

    retention_days = int(config.get("monitoring", {}).get("event_log_retention_days", 1))
    cutoff = datetime.now() - timedelta(days=retention_days)

    def parse_dt(s: str) -> datetime | None:
        s = (s or "").strip()
        if not s:
            return None

        # Common BigQuery DATETIME string
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                pass

        # Fractional seconds
        if "." in s:
            base = s.split(".", 1)[0]
            try:
                return datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        # ISO-ish
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None

    # Keep only within retention window from existing.
    kept: list[dict[str, Any]] = []
    for e in existing:
        rec_dt = parse_dt(str(e.get("rec_dt", "")))
        if rec_dt is None:
            # Fall back to detected_at (controlled by us) so we never drop rows
            # just because rec_dt format changed.
            rec_dt = parse_dt(str(e.get("detected_at", "")))
        if rec_dt is not None and rec_dt >= cutoff:
            kept.append(e)

    # Build index by event key so we can merge updates.
    index: dict[str, dict[str, Any]] = { _event_key_from_dict(e): e for e in kept }

    for e in events:
        key = e.event_id()
        if key in index:
            # Update mutable fields (vendor name might appear later if join toggled on, etc.)
            index[key].update(
                {
                    "rec_dt": e.rec_dt,
                    "location_id": e.location_id,
                    "container_id": e.container_id,
                    "item_nbr": e.item_nbr,
                    "vendor_name": e.vendor_name,
                    "delivery_number": e.delivery_number,
                    "shift_label": e.shift_label,
                "case_qty": e.case_qty,
                    "case_qty": e.case_qty,
                }
            )
        else:
            index[key] = {
                "rec_dt": e.rec_dt,
                "location_id": e.location_id,
                "container_id": e.container_id,
                "item_nbr": e.item_nbr,
                "vendor_name": e.vendor_name,
                "delivery_number": e.delivery_number,
                "shift_label": e.shift_label,
                "case_qty": e.case_qty,
                "detected_at": _now_iso(),
            }

    merged = list(index.values())
    merged.sort(key=lambda x: str(x.get("rec_dt", "")), reverse=True)
    save_events_log(merged)


def _write_dashboard_html(config: dict[str, Any]) -> None:
    """Write the dashboard file.

    For UI development we just serve the template file (which pulls live data from /api/events + /api/status).
    Keeping HTML out of Python = less pain.

    (Westly embedded HTML, but that’s optional. DRY > nostalgia.)
    """

    # Always ensure a dashboard exists.
    if TEMPLATE_PATH.exists():
        DASHBOARD_PATH.write_text(TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        return

    # Fallback (should never happen)
    DASHBOARD_PATH.write_text(
        "<html><body><h1>Dashboard template missing</h1></body></html>",
        encoding="utf-8",
    )


def _write_analytics_html(config: dict[str, Any]) -> None:
    """Write the analytics page file (served at /analytics)."""

    if ANALYTICS_TEMPLATE_PATH.exists():
        ANALYTICS_PATH.write_text(
            ANALYTICS_TEMPLATE_PATH.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return

    # Fallback (non-fatal)
    ANALYTICS_PATH.write_text(
        "<html><body><h1>Analytics template missing</h1></body></html>",
        encoding="utf-8",
    )


def _write_viz_html(config: dict[str, Any]) -> None:
    """Write the visualizations page file (served at /viz)."""

    if VIZ_TEMPLATE_PATH.exists():
        VIZ_PATH.write_text(VIZ_TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        return

    VIZ_PATH.write_text(
        "<html><body><h1>Viz template missing</h1></body></html>",
        encoding="utf-8",
    )


def _write_roster_html(config: dict[str, Any]) -> None:
    """Write the roster management page file (served at /roster)."""

    if ROSTER_TEMPLATE_PATH.exists():
        ROSTER_PATH.write_text(ROSTER_TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        return

    ROSTER_PATH.write_text(
        "<html><body><h1>Roster template missing</h1></body></html>",
        encoding="utf-8",
    )


def _start_flask_server_subprocess() -> None:
    # Start the server as a child process.
    # This matches the “two python processes” described in the docs.
    python_exe = sys.executable
    subprocess.Popen(
        [python_exe, str(BASE_DIR / "atc_data_server.py")],
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_once(config: dict[str, Any]) -> tuple[list[AtcEvent], list[AtcEvent]]:
    sql = _bq_query_sql(config)
    # BigQuery job project controls where the query job runs/bills.
    # Tables still live in wmt-edw-prod; this just changes job ownership/slots.
    job_project = config.get("bigquery", {}).get("job_project")
    billing_project = config.get("bigquery", {}).get("billing_project")
    project_id = job_project or billing_project

    csv_text = _run_bq_query(config, sql, billing_project=project_id)
    events = _parse_events_csv(csv_text)

    lookback_minutes = int(config.get("monitoring", {}).get("lookback_minutes", 15))
    recent = _filter_recent(events, lookback_minutes=lookback_minutes)

    state = load_state()
    seen: set[str] = set(state.get("seen_event_ids", []))

    new_events = [e for e in recent if e.event_id() not in seen]

    # Update state to reflect everything we’ve seen in the last 24h query.
    # This prevents dupes even if the lookback window changes.
    updated_seen = list(seen.union({e.event_id() for e in events}))
    save_state(updated_seen)

    return events, new_events


def _write_status(config: dict[str, Any], **updates: Any) -> None:
    # Keep status always readable even if we crash mid-write.
    payload: dict[str, Any] = {}
    if STATUS_PATH.exists():
        try:
            payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}

    payload.setdefault("facility_id", config.get("monitoring", {}).get("facility_id"))
    payload.setdefault("tableau_url", str(config.get("dashboard", {}).get("tableau_url", "")).strip())
    payload.update(updates)

    STATUS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    config = load_config()

    _write_dashboard_html(config)
    _write_analytics_html(config)
    _write_viz_html(config)
    _write_roster_html(config)
    # Ensure event log exists so the dashboard API always has something to serve.
    if not EVENTS_LOG_PATH.exists():
        save_events_log([])

    _write_status(config, state="starting", last_query_start=None, last_query_end=None, last_error=None)

    print(f"[INIT] Manual Receiving ATC starting ({config['monitoring']['facility_id']})", flush=True)
    print("[INIT] Starting local dashboard server on http://localhost:5000", flush=True)
    _start_flask_server_subprocess()

    polling_interval = float(config.get("monitoring", {}).get("polling_interval_minutes", 15))

    # Safety config (defaults are conservative)
    safety = config.get("safety", {})
    kill_switch_file = str(safety.get("kill_switch_file", "STOP_ATC.txt"))
    max_queries_per_hour = int(safety.get("max_queries_per_hour", 12))
    max_consecutive_failures = int(safety.get("max_consecutive_failures", 3))
    backoff_on_error_seconds = int(safety.get("backoff_on_error_seconds", 600))

    # In-memory rate limit: track query starts in the last hour.
    recent_query_starts: deque[float] = deque()
    consecutive_failures = 0

    def kill_switch_active() -> bool:
        return (BASE_DIR / kill_switch_file).exists()

    while True:
        # Kill switch (drop a STOP_ATC.txt in the folder)
        if kill_switch_active():
            msg = f"Kill switch detected ({kill_switch_file}). Stopping ATC."
            print(f"[ALERT] {msg}", flush=True)
            _write_status(config, state="stopped", last_error=msg)
            raise SystemExit(0)

        # Rate limit (max queries per hour)
        now = time.time()
        one_hour_ago = now - 3600
        while recent_query_starts and recent_query_starts[0] < one_hour_ago:
            recent_query_starts.popleft()

        if len(recent_query_starts) >= max_queries_per_hour:
            msg = (
                f"Rate limit hit: {len(recent_query_starts)} queries in the last hour "
                f"(max={max_queries_per_hour}). Pausing queries." 
            )
            print(f"[ALERT] {msg}", flush=True)
            _write_status(config, state="paused", last_error=msg)
            time.sleep(max(60, backoff_on_error_seconds))
            continue

        cycle_start = time.time()
        recent_query_starts.append(cycle_start)

        try:
            print("[INFO] Querying BigQuery...", flush=True)
            _write_status(
                config,
                state="running",
                last_query_start=_now_iso(),
                last_query_end=None,
                last_error=None,
                query_duration_seconds=None,
            )

            events, new_events = run_once(config)
            upsert_events_to_log(events, config)

            # Delivery emails (outbox preview mode while Graph admin consent is pending)
            email_cfg = config.get("email_notifications", {})
            if bool(email_cfg.get("enabled", False)) or bool(email_cfg.get("preview_outbox", True)):
                new_event_dicts = [
                    {
                        "rec_dt": e.rec_dt,
                        "location_id": e.location_id,
                        "container_id": e.container_id,
                        "item_nbr": e.item_nbr,
                        "vendor_name": e.vendor_name,
                        "delivery_number": e.delivery_number,
                        "shift_label": e.shift_label,
                        "case_qty": e.case_qty,
                    }
                    for e in new_events
                ]
                notify_new_deliveries(base_dir=BASE_DIR, config=config, new_events=new_event_dicts)

            # success resets breaker
            consecutive_failures = 0

            notifications_enabled = bool(config.get("notifications", {}).get("enabled", True))
            if new_events:
                print(f"[ALERT] {len(new_events)} new event(s)", flush=True)
                if notifications_enabled:
                    for e in new_events:
                        _send_notification(config, e)
                else:
                    print("[INFO] Notifications disabled (config.notifications.enabled=false)", flush=True)
            else:
                print("[OK] No new events", flush=True)

            duration = round(time.time() - cycle_start, 2)
            _write_status(config, state="running", last_query_end=_now_iso(), query_duration_seconds=duration)

            # Sleep remaining time in the interval
            target = polling_interval * 60.0
            elapsed = time.time() - cycle_start
            sleep_seconds = max(5.0, target - elapsed)
            print(f"[INFO] Sleeping {round(sleep_seconds, 1)}s until next cycle...", flush=True)
            time.sleep(sleep_seconds)

        except Exception as e:
            consecutive_failures += 1
            duration = round(time.time() - cycle_start, 2)
            print(f"[ERROR] {e}", flush=True)
            _write_status(
                config,
                state="error",
                last_error=str(e),
                last_query_end=_now_iso(),
                query_duration_seconds=duration,
            )

            if consecutive_failures >= max_consecutive_failures:
                msg = (
                    f"Circuit breaker tripped: {consecutive_failures} consecutive failures "
                    f"(max={max_consecutive_failures}). Stopping ATC to prevent runaway queries."
                )
                print(f"[ALERT] {msg}", flush=True)
                _write_status(config, state="stopped", last_error=msg)
                raise SystemExit(1)

            print(f"[INFO] Backing off for {backoff_on_error_seconds}s after error...", flush=True)
            time.sleep(max(60, backoff_on_error_seconds))


if __name__ == "__main__":
    main()