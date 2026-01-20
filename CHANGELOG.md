# Changelog

## v1.0.0
- Operations dashboard (last 24h table, last hour KPIs)
- Config-driven overflow location exclusion (EOF/WOF)
- Alerts/notifications can be disabled via config
- BigQuery job project configurable (slot/reservation control)
- Safety failsafes: kill switch, rate limit, circuit breaker, backoff
- Analytics page (/analytics): Top manually received items (30d) on-demand + cached
- Windows-safe BigQuery invocation via Cloud SDK bootstrapping (bq.py)

