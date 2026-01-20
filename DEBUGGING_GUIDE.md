# Manual Receiving ATC (US-07377) — Debugging Guide

## 1) Start in DEBUG mode

Run:
- `Step 2 - START ATC DEBUG.bat`

You should see logs like:
- `[INIT] Manual Receiving ATC starting (US-07377)`
- `[INFO] Querying BigQuery...`
- `[OK] No new events`

If you see `[ERROR] ...`, keep reading.

---

## 2) Safety / Failsafes (prevents runaway BigQuery querying)

### A) Kill switch (manual stop)

If you need ATC to stop querying immediately:
1. Create an empty file in the ATC folder named:
   - `STOP_ATC.txt`
2. ATC will detect it and exit gracefully.

To restart:
- Delete `STOP_ATC.txt` and start ATC again.

### B) Rate limit

ATC enforces a max number of query runs per hour (default: 12).
If it hits that limit it will pause querying for a while instead of hammering BigQuery.

### C) Circuit breaker

If ATC hits too many consecutive failures (default: 3), it will stop itself to prevent
runaway retry loops.

All of these are configurable in `atc_config.json` under the `safety` section.

---

## 3) Common failures

### A) `bq` not found

Symptoms:
- `[ERROR] [WinError 2] ... bq ...`

Fix:
- Install Google Cloud SDK
- Ensure `bq` is on PATH
- Verify:
  - `bq --version`

---

### B) Permission denied / auth errors

Fix:
- `gcloud auth login`
- `gcloud auth application-default login`
- Verify:
  - `bq ls --project_id=wmt-edw-prod`

If you still get access errors, you likely need BigQuery permissions for the datasets/tables.

---

### C) Dashboard doesn’t load (http://localhost:5000)

Possible causes:
- ATC not running
- Port 5000 is in use

What to do:
1. Confirm ATC is running (in DEBUG mode you’ll see logs)
2. If port conflict:
   - set env var before starting (advanced):
     - `set ATC_PORT=5001`
   - then run the debug starter from that same terminal
   - open `http://localhost:5001`

---

### D) No notifications appear

Possible causes:
- No new events during your lookback window
- Windows notifications disabled

Try:
- In Windows: Settings → System → Notifications
- Ensure notifications are enabled
- Wait for an actual new event

---

## 3) Where files live

In the same folder as the app:
- `atc_config.json` — config
- `atc_state.json` — “seen” event IDs (prevents duplicate notifications)
- `atc_events_log.json` — last 24 hours of events
- `atc_dashboard.html` — generated dashboard

---

## 4) Resetting the system (careful)

If you want to “start fresh” (or after major logic changes like event identity rules):
- Stop ATC
- Delete:
  - `atc_state.json`
  - `atc_events_log.json`
  - `atc_dashboard.html`

Then start again.

Note:
- This ATC treats **CONTAINER_ID as the unique event key**.
- If you previously ran a version that used a different event key, you should reset
  so the log/state rebuild cleanly.
