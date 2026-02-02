# Changelog

## Unreleased
- Removed Roster page + API; added Deliveries page (/deliveries) with delivery-level notification history table.

## v3.0.0
- Site-hosted web dashboard support (LAN host mode) + hosting docs
- Teams shift-channel notifications via Incoming Webhooks (A1/A2/B1)
- Browser alerts with clean in-page toasts, per-session baseline, and sound
- Item descriptions (item_desc) added to events, dashboard tables, analytics, and notifications
- Overflow location filtering hardened (case-insensitive) at query + API layers
- UI density improvements (less whitespace, key tables side-by-side)

## v2.0.0
- Visualizations page (/viz) with ops-focused charts and time-range toggles
- Roster page (/roster) with drag/drop inbound shift assignments
- Email template builder + outbox preview for delivery-based MR notifications (Graph pending admin consent)
- Top-items analytics query improvements and config tuning
- Local event log retention extended to 7 days
- Navigation tabs moved to top across pages

## v1.0.0
- Operations dashboard (last 24h table, last hour KPIs)
- Config-driven overflow location exclusion (EOF/WOF)
- Alerts/notifications can be disabled via config
- BigQuery job project configurable (slot/reservation control)
- Safety failsafes: kill switch, rate limit, circuit breaker, backoff
- Analytics page (/analytics): Top manually received items (30d) on-demand + cached
- Windows-safe BigQuery invocation via Cloud SDK bootstrapping (bq.py)

