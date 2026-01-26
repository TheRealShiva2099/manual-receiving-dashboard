from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from atc_teams_webhook import TeamsWebhookConfig, post_teams_message


BASE_DIR = Path(__file__).resolve().parent
CFG_PATH = BASE_DIR / "atc_config.json"


def main() -> None:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    teams = cfg.get("teams_notifications", {})
    hooks = teams.get("webhooks_by_shift", {}) or {}

    shift = (sys.argv[1] if len(sys.argv) > 1 else "Shift A1").strip()
    url = str(hooks.get(shift, "")).strip()
    if not url:
        raise SystemExit(f"No webhook configured for shift: {shift}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"[ATC] Test message ({shift})"
    lines = [
        f"This is a test Teams message from Manual Receiving ATC.",
        f"Shift: {shift}",
        f"Time: {now}",
        f"Host: {cfg.get('monitoring', {}).get('facility_id', '-')}",
    ]

    post_teams_message(cfg=TeamsWebhookConfig(webhook_url=url), title=title, lines=lines)
    print(f"OK: posted test message to Teams channel webhook for {shift}")


if __name__ == "__main__":
    main()
