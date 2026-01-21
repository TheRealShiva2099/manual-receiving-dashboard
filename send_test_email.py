from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from graph_email_sender import GraphConfig, send_mail


BASE_DIR = Path(__file__).resolve().parent
CFG_PATH = BASE_DIR / "atc_config.json"


def main() -> None:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    email_cfg = cfg.get("email_notifications", {})
    graph = email_cfg.get("graph", {})

    gc = GraphConfig(
        tenant=str(graph.get("tenant", "common")),
        client_id=str(graph.get("client_id", "")),
        sender=str(graph.get("sender", "")),
        token_cache_file=str(graph.get("token_cache_file", "msal_token_cache.bin")),
    )

    to = email_cfg.get("recipients", []) or [gc.sender]
    to = [str(x) for x in to if str(x).strip()]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[ATC] Graph email test ({now})"
    html = (
        f"<h2>Manual Receiving ATC - Graph Test</h2>"
        f"<p>This is a test email sent via Microsoft Graph.</p>"
        f"<ul>"
        f"<li>Sender: {gc.sender}</li>"
        f"<li>Recipients: {', '.join(to)}</li>"
        f"<li>Time: {now}</li>"
        f"</ul>"
    )

    print("Sending test email via Microsoft Graph...", flush=True)
    send_mail(cfg=gc, subject=subject, html_body=html, to_recipients=to)
    print("OK: sendMail accepted by Graph (check your inbox + Sent Items)")


if __name__ == "__main__":
    main()
