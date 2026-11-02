from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SummaryReport(BaseModel):
    generated_at: datetime
    generated_by: str
    window: dict[str, datetime | None]
    totals: dict[str, int]
    label_distribution: dict[str, int]
    risk_band_distribution: dict[str, int]
    alerts_by_status: dict[str, int]
    alerts_by_disposition: dict[str, int]
    jobs: dict[str, int]
    models: list[dict[str, Any]]
    notes: list[str]
