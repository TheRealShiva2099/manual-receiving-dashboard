# Changelog

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

