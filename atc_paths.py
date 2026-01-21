from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AtcPaths:
    """Centralized paths for ATC runtime files (SRP)."""

    base_dir: Path

    @property
    def config(self) -> Path:
        return self.base_dir / "atc_config.json"

    @property
    def state(self) -> Path:
        return self.base_dir / "atc_state.json"

    @property
    def email_state(self) -> Path:
        return self.base_dir / "atc_email_state.json"

    @property
    def events_log(self) -> Path:
        return self.base_dir / "atc_events_log.json"

    @property
    def status(self) -> Path:
        return self.base_dir / "atc_status.json"

    @property
    def dashboard_html(self) -> Path:
        return self.base_dir / "atc_dashboard.html"

    @property
    def dashboard_template(self) -> Path:
        return self.base_dir / "dashboard_template.html"

    @property
    def analytics_html(self) -> Path:
        return self.base_dir / "atc_analytics.html"

    @property
    def analytics_template(self) -> Path:
        return self.base_dir / "analytics_template.html"

    @property
    def viz_html(self) -> Path:
        return self.base_dir / "atc_viz.html"

    @property
    def viz_template(self) -> Path:
        return self.base_dir / "viz_template.html"

    @property
    def last_query(self) -> Path:
        return self.base_dir / "last_atc_query.sql"
