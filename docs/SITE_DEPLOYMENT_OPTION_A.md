# Option A (This Week): Site-only deployment on a dedicated PC/VM

Goal: make the ATC dashboard reachable to your building/site without requiring end users to install anything.

This is the “fast + practical” approach.

---

## Architecture
- One always-on host in your building/site (PC or VM)
- ATC runs continuously on that host
- Users access it via a browser: `http://<host>:5000/` (or HTTPS via reverse proxy)

No extra BigQuery load compared to today.

---

## 0) Pick the host
Recommended:
- A site VM (better uptime) or a dedicated “ATC kiosk” PC.
- Must be reachable from manager workstations (same network/VLAN).

Avoid:
- Your personal laptop.

---

## 1) Install / configure ATC on the host
1. Copy the project folder to the host
   - e.g. `C:\ATC\my_manual_receiving_atc\`
2. Run:
   - `Step 1 - INSTALL.bat`
3. Validate BigQuery connectivity:
   - `Step 0 - BQ SMOKE TEST (Debug).bat`
4. Start ATC:
   - `Step 2 - START ATC (Silent).bat`

---

## 2) Run it "as a service" (recommended)
### Option A2.1: Windows Scheduled Task (best quick win)
Create a scheduled task that:
- runs at startup
- runs whether user is logged in or not
- restarts on failure

Suggested action:
- Program/script: `cmd.exe`
- Arguments: `/c "C:\ATC\my_manual_receiving_atc\Step 2 - START ATC (Silent).bat"`
- Start in: `C:\ATC\my_manual_receiving_atc`

Set:
- Restart on failure: yes
- Stop task if it runs longer than: **disabled**

### Option A2.2: NSSM (optional)
If allowed, NSSM can wrap python as a Windows service. Use only if your site allows installing it.

---

## 3) Open firewall port (HTTP)
Default server port is 5000.

On the host, open inbound TCP:
- Port: `5000`
- Scope: restrict to your building subnet if possible.

If Windows Firewall is used, this is typically:
- Windows Defender Firewall → Inbound Rules → New Rule → Port → TCP 5000 → Allow

---

## 4) DNS / hostname (optional but makes it nicer)
Ask your site IT for an internal DNS entry:
- `mr-atc-7377` → host IP

Then users can hit:
- `http://mr-atc-7377:5000/`

---

## 5) Basic hardening (do this, even for a site-only app)
- Keep `ATC_HOST=127.0.0.1` is **not** valid for site access.
- Set Flask bind host to `0.0.0.0` only on this server host.

Where:
- Update how `atc_data_server.py` runs (or set environment variable)

Environment variables to set on the server host:
- `ATC_HOST=0.0.0.0`
- `ATC_PORT=5000`

Also recommended:
- Host should be patched and have endpoint protection.
- Restrict inbound firewall scope to the site subnet.

---

## 6) HTTPS (optional, but better)
Fastest: reverse proxy with IIS (or nginx) on the host.

### IIS reverse proxy (high-level)
- Install IIS + URL Rewrite + ARR
- Create a site bound to HTTPS 443
- Reverse proxy to `http://127.0.0.1:5000`

Benefits:
- `https://mr-atc-7377/` with no port in URL

---

## 7) Ops runbook
- Start/stop: use the batch files
- Kill switch: create `STOP_ATC.txt` in the folder
- Logs:
  - ATC writes status to `atc_status.json`
  - Email outbox (preview) writes to `outbox_emails/`

---

## 8) Known limitations
- No SSO: anyone on the network who can reach the host can view it.
- Deliveries history: anyone who can reach `/deliveries` can view notification history (read-only).
- Scaling: one host.

---

## Recommended next improvement (still Option A)
- Add simple access control:
  - network restriction + a shared password prompt, or
  - integrate with site SSO (harder).

