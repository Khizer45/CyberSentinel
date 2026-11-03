"""Versioned risk-scoring policy (ML-07, SRS 1.4 "Threat Scoring").

The policy turns model outputs into an **application policy score** on a 0–100 scale and a band
(low/medium/high/critical). It is *not* a probability. The full formula is documented in
``docs/risk_scoring_policy.md`` and implemented in :mod:`app.ml.risk.scoring`.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ml.constants import RISK_BAND_ORDER, RiskBand, risk_band_rank


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Weights(_Strict):
    classifier: float = Field(ge=0, le=1)
    anomaly: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _sum_to_one(self) -> Weights:
        if abs(self.classifier + self.anomaly - 1.0) > 1e-9:
            raise ValueError("weights.classifier + weights.anomaly must equal 1")
        return self


class CategoryWeights(_Strict):
    """Severity multiplier per predicted attack category, in [0, 1]."""

    default: float = Field(default=1.0, ge=0, le=1)
    overrides: dict[str, float] = Field(default_factory=dict)

    @field_validator("overrides")
    @classmethod
    def _in_range(cls, value: dict[str, float]) -> dict[str, float]:
        for name, weight in value.items():
            if not 0 <= weight <= 1:
                raise ValueError(f"category weight for {name!r} must be within [0, 1]")
        return value

    def weight_for(self, category: str) -> float:
        return self.overrides.get(category, self.default)


class Floors(_Strict):
    """Minimum risk score applied when a condition holds (keeps such rows in analyst view)."""

    anomaly: float = Field(default=25.0, ge=0, le=100)
    needs_review: float = Field(default=25.0, ge=0, le=100)


class Band(_Strict):
    name: RiskBand
    min_score: float = Field(ge=0, le=100)


class Alerting(_Strict):
    min_band: RiskBand = RiskBand.HIGH
    alert_on_anomaly: bool = False
    alert_on_needs_review: bool = False


class RiskPolicy(_Strict):
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(max_length=2000)
    weights: Weights
    category_weights: CategoryWeights = CategoryWeights()
    floors: Floors = Floors()
    bands: list[Band]
    alerting: Alerting = Alerting()

    @model_validator(mode="after")
    def _valid_bands(self) -> RiskPolicy:
        names = [band.name for band in self.bands]
        if tuple(names) != RISK_BAND_ORDER:
            raise ValueError("bands must list low, medium, high, critical in this order")
        mins = [band.min_score for band in self.bands]
        if mins[0] != 0 or any(b <= a for a, b in pairwise(mins)):
            raise ValueError("band min_score values must start at 0 and strictly increase")
        return self

    def band_for(self, score: float) -> RiskBand:
        chosen = self.bands[0].name
        for band in self.bands:
            if score >= band.min_score:
                chosen = band.name
        return chosen

    def is_alert_band(self, band: str) -> bool:
        return risk_band_rank(band) >= risk_band_rank(self.alerting.min_band)


def load_policy(path: Path) -> RiskPolicy:
    """Load and validate a policy file. Raises ``ValueError``/``ValidationError`` when invalid."""
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return RiskPolicy.model_validate(data)
