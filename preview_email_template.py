from __future__ import annotations

from datetime import datetime
from pathlib import Path

from atc_email_template import DeliveryEmailSummary, DeliveryItemLine, build_html, build_subject


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "outbox_emails"
    out_dir.mkdir(parents=True, exist_ok=True)

    s = DeliveryEmailSummary(
        facility_id="US-07377",
        shift_label="Shift A1",
        delivery_number="668675031",
        first_detected_local=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        locations=["301", "317", "CP08FL_C-1"],
        total_cases=128.0,
        items=[
            DeliveryItemLine(
                item_nbr="680855174",
                vendor_name="ACME VENDOR INC",
                cases=96.0,
                locations=["301", "317"],
            ),
            DeliveryItemLine(
                item_nbr="666234981",
                vendor_name="OTHER VENDOR LLC",
                cases=32.0,
                locations=["CP08FL_C-1"],
            ),
        ],
    )

    html = build_html(s)
    subject = build_subject(s)

    path = out_dir / "preview_email.html"
    path.write_text(html, encoding="utf-8")

    print("Wrote:", path)
    print("Subject:", subject)


if __name__ == "__main__":
    main()
