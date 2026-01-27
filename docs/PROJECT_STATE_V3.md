# Manual Receiving Dashboard — Project State (v3.0.0)

Last updated: 2026-01-22

This document is the "drop-in context" for a new Code Puppy session.

---

## What this is
A site-only, lightweight web dashboard for **Manual Receiving** at facility **US-07377**.

It:
- Polls BigQuery on a schedule to detect manual receiving events.
- Serves a local website (Flask) that anyone on the site LAN can open.
- Sends shift-routed notifications via **Teams channel Incoming Webhooks**.
- Provides in-browser alerts (toast + sound) for users with the page open.

---

## Current version / git checkpoints
- **v1.0.0** tag: baseline
- **v2.0.0** tag: initial dashboard/viz/analytics/roster + email template + outbox
- **v3.0.0** tag: site-hosted + Teams notifications + browser toasts + item_desc + hardened overflow filtering + UI density

Branch:
- `v3` is the active branch containing v3.0.0.

---

## How to run (developer / debug)
### Install
Run:
- `Step 1 - INSTALL.bat`

### BigQuery smoke test
Run:
- `Step 0 - BQ SMOKE TEST (Debug).bat`

### Start ATC (debug)
Run:
- `Step 2 - START ATC DEBUG.bat`

### Start ATC (silent)
Run:
- `Step 2 - START ATC (Silent).bat`

### Start ATC (LAN host)
Run:
- `Step 2 - START ATC (LAN Host).bat`

LAN hosting allows coworkers on the same network to access:
- `http://<host-ip>:5000/`

Docs:
- `docs/HOSTING_ON_LAPTOP.md`
- `docs/FRIENDLY_URLS.md`

---

## Web pages
All served by `atc_data_server.py`.

- `/` — Operations dashboard (main)
- `/viz` — Visualizations (charts) using local event log (no extra BQ load)
- `/analytics` — Top items analytics endpoint backed by BigQuery (on-demand refresh)
- `/roster` — Shift roster management (drag/drop)

Navigation tabs are at the top of pages.

---

## Key features implemented
### 1) BigQuery event polling
`manual_receiving_atc.py` builds and runs a BigQuery query via `bq` CLI.

Important columns returned:
- `rec_dt`
- `location_id`
- `container_id`
- `item_nbr`
- `item_desc`  ✅ pulled from `CONTAINER_ITEM_OPERATIONS`
- `vendor_name` (optional join)
- `delivery_number`
- `case_qty` (computed)
- `shift_label` (computed)

Duplicates reduction:
- Latest `RECEIVING_ITEM` per container (and item where needed)
- Container→item mapping preserves item granularity (no ANY_VALUE(item_nbr) mistakes)

Overflow filtering:
- Config-driven `overflow_locations` (EOF/WOF)
- Filtered **case-insensitively**
  - in BigQuery SQL
  - and again in the API layer (`/api/events`)

### 2) Local state files
Stored in the project directory.

- `atc_events_log.json`
  - event log (retention configurable, currently 7 days)
- `atc_state.json`
  - internal state for dedupe/lookback behavior
- `atc_status.json`
  - server status for UI pills
- `atc_roster.json`
  - inbound roster by shift (inbound only)
- `atc_email_state.json`
  - notification state (delivery dedupe + per-hour rate limit buckets)
- `outbox_emails/`
  - audit trail of generated notification HTML/metadata

### 3) Shift roster page
- `/roster`
- Inbound-only (outbound removed explicitly)
- Drag/drop manager emails into shift buckets.
- Backend endpoints:
  - `GET /api/roster`
  - `POST /api/roster`

Note: roster currently does NOT control Teams channel membership. Teams channel membership is separate and would require Graph or Power Automate.

### 4) Notifications
#### A) Teams channel notifications (primary)
Implemented via Incoming Webhooks (no Graph admin consent needed).

- Config: `teams_notifications` in `atc_config.json`
- Webhook URLs per shift:
  - Shift A1 ✅ configured
  - Shift A2 ✅ configured
  - Shift B1 ✅ configured
  - Off Shift: intentionally ignored (no webhook)

Delivery dedupe:
- one notification per `delivery_number`

Message content:
- includes facility, shift, first detected, delivery number, locations (non-overflow), and top items with item_desc
- intentionally does NOT include case counts

Test script:
- `send_test_teams.py` (shift arg optional)

#### B) Browser alerts (for users with page open)
Implemented as:
- In-page toast popups + short beep
- Optional OS Notification API (often blocked on http://IP)

Behavior:
- Alerts only trigger for deliveries **after the page load/refresh** (session baseline)
- Includes location + item_nbr + item_desc

#### C) Email notifications (deferred)
- Microsoft Graph device-code flow implemented (`graph_email_sender.py`, `send_test_email.py`)
- Blocked by admin consent for `Mail.Send`
- Outbox HTML generation exists for audit/review.

### 5) Analytics
- `/analytics` page uses `/api/top-items`
- `/api/top-items` runs BigQuery and caches results in `top_items_cache.json`
- Now includes `item_desc` column.

---

## Config summary (`atc_config.json`)
Important keys:
- `monitoring.facility_id`
- `monitoring.query_window_minutes`
- `monitoring.polling_interval_minutes`
- `monitoring.overflow_locations` (EOF/WOF)
- `notifications.enabled` (local Windows plyer notifications — host machine only)
- `teams_notifications.enabled` ✅ true in v3
- `teams_notifications.webhooks_by_shift` ✅ A1/A2/B1 set
- `email_notifications.enabled` false (Graph blocked)

---

## Hosting (this week)
We’re using **Option A**:
- host is a laptop/PC
- Flask binds to `0.0.0.0` via `ATC_HOST`
- firewall allows TCP 5000

Docs:
- `docs/SITE_DEPLOYMENT_OPTION_A.md`
- `docs/LONG_TERM_DEPLOYMENT_OPTION_B.md`

---

## Known gotchas / fixes applied
- Windows console encoding issues caused crashes due to Unicode punctuation in source comments.
  - removed non-ascii punctuation.
- Overflow locations were leaking because source emitted lowercase `eof`.
  - fixed with case-insensitive filtering in SQL + API.
- Dashboard went blank due to JS runtime errors (missing descCounts).
  - fixed and added defensive error surfacing.

---

## Where to look for core logic
- Main loop + query building: `manual_receiving_atc.py`
- Flask server + API endpoints: `atc_data_server.py`
- Delivery-level notification aggregation: `atc_delivery_notifications.py`
- Teams webhook sender: `atc_teams_webhook.py`
- Browser UI: `dashboard_template.html` (and generated `atc_dashboard.html`)

---

## Next steps (recommended)
Short-term:
- Decide if Off Shift should notify anywhere.
- Add a simple auth gate for `/roster` (at least a shared password) since it’s site-hosted.
- Consider a one-click “purge overflow events from local log” utility.

Long-term (Option B):
- Move state from JSON files to Postgres.
- Replace `bq` CLI with BigQuery SDK + service identity.
- Add Entra SSO.
- Replace Teams webhooks with Graph messages if DM/@mention is needed.

---

## Copy/paste for future session
"Please read `docs/PROJECT_STATE_V3.md` to get up to speed on the Manual Receiving Dashboard project (v3.0.0)." 
