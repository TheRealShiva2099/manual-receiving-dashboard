# Option B (Long-term): Containerized, authenticated internal web app

Goal: a maintainable, secure deployment that can run 24/7 on a managed platform.

This is the “do it right” plan.

---

## Target architecture (recommended)
**Web app**
- FastAPI (or Flask) serving UI + APIs
- Entra ID (Azure AD) SSO authentication

**Worker / scheduler**
- Background worker (Celery/RQ/APS cheduler) or a cron-style job
- Polls BigQuery every N minutes

**State storage**
- Postgres (recommended boring choice)
  - tables: events, deliveries_notified, roster, settings

**Email**
- Microsoft Graph sendMail
  - from a shared mailbox or service identity

**Hosting**
- Kubernetes (internal) or managed app service
- Container image built in CI and deployed via CD

---

## What changes from Option A
### Replace local JSON files
Current:
- `atc_events_log.json`, `atc_state.json`, `atc_roster.json`, `atc_email_state.json`

Long-term:
- store all state in Postgres

### Stop using `bq` CLI
Current:
- shelling out to Cloud SDK

Long-term:
- use BigQuery Python client
- run under a service account identity

---

## Permissions / approvals checklist
### 1) Platform access
- Namespace / subscription access for the hosting platform
- Ability to deploy containers
- Ingress / DNS for the site hostname

### 2) BigQuery access
Preferred: **service account**
- Create service account in appropriate project
- Grant BigQuery permissions:
  - `bigquery.jobs.create` in the job/billing project
  - `bigquery.dataViewer` (or dataset/table-level read) on required datasets

Also:
- confirm slot reservation / billing project

### 3) Microsoft Graph email permissions
Two main models:

**A) Delegated (user context)**
- requires interactive sign-in (not great for server)

**B) Application permissions (recommended for servers)**
- App registration with **Application** permissions:
  - `Mail.Send`
- Admin consent required
- Mailbox to send from:
  - shared mailbox or service mailbox

### 4) Entra SSO for the web app
- App registration for the web app
- Redirect URIs
- Group/role claims if you want RBAC:
  - allow only certain AD groups to view/edit roster

### 5) Secrets management
- Store secrets in a managed secret store (Key Vault etc)
- Never commit secrets to git

---

## CI/CD steps (high-level)
1. Create Dockerfile
2. Build in CI
3. Push image to internal registry
4. Deploy via Helm/Kustomize/app-service pipeline
5. Run DB migrations

---

## Recommended v3→v4 migration path
1) Move roster + email state from JSON → Postgres
2) Move events log from JSON → Postgres
3) Replace bq CLI with BigQuery SDK
4) Add Entra SSO to UI
5) Replace delegated Graph auth with application permission

---

## Data model (suggested)
- `events`
  - id, container_id, rec_dt, location_id, item_nbr, vendor_name, delivery_number, shift_label, case_qty
- `deliveries_notified`
  - delivery_number, first_seen_dt, notified_dt
- `roster_inbound`
  - shift_label, email

---

## Operational requirements
- Monitoring/alerts for:
  - worker failures
  - BigQuery errors/timeouts
  - email send failures
- Audit log:
  - roster changes
  - notification sends

