"""CSV/JSON exports of authorized result sets and summary reports (SRS 1.4 Reporting, PRD US4).

Exports stream from the database in batches (bounded memory), are capped at ``EXPORT_MAX_ROWS``, escape
spreadsheet formulas, and only contain rows the requesting user may read (the query applies the same ownership
filters as the list endpoints).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_database
from app.db.types import utcnow
from app.models import AnalysisJob, Prediction, User
from app.repositories import metrics as metrics_repo
from app.repositories import model_versions as model_repo
from app.repositories import predictions as prediction_repo
from app.repositories.analysis_jobs import status_counts
from app.utils.csv_safety import escape_csv_cell

PREDICTION_COLUMNS = [
    "record_index",
    "predicted_label",
    "classifier_score",
    "probability",
    "anomaly_score",
    "is_anomaly",
    "risk_score",
    "risk_band",
    "is_alert",
    "true_label",
    "created_at",
]
ALERT_COLUMNS = [
    "id",
    "analysis_job_id",
    "dataset_name",
    "model_name",
    "model_version",
    "record_index",
    "predicted_label",
    "risk_score",
    "risk_band",
    "anomaly_score",
    "is_anomaly",
    "classifier_score",
    "probability",
    "status",
    "latest_disposition",
    "review_count",
    "created_at",
]


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "hex") and not isinstance(value, (str, bytes)):
        return str(value)
    return value


def _csv_line(values: list[Any]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerow([escape_csv_cell(_jsonable(v)) if v is not None else "" for v in values])
    return buffer.getvalue()


def prediction_export_stream(job: AnalysisJob, filters: dict[str, Any], *, fmt: str, max_rows: int) -> Iterator[str]:
    meta = {
        "analysis_job_id": str(job.id),
        "model_name": job.model_version.model_name,
        "model_version": job.model_version.version,
        "risk_policy_version": job.risk_policy_version,
    }
    first = True
    if fmt == "csv":
        yield _csv_line([*PREDICTION_COLUMNS, *meta.keys()])
    else:
        yield "["
    with get_database().session() as session:
        for batch in prediction_repo.iter_job_predictions(session, job.id, filters, max_rows=max_rows):
            for row in batch:
                values = [getattr(row, c) for c in PREDICTION_COLUMNS]
                if fmt == "csv":
                    yield _csv_line([*values, *meta.values()])
                else:
                    record = {c: _jsonable(v) for c, v in zip(PREDICTION_COLUMNS, values, strict=True)} | meta
                    yield ("" if first else ",") + json.dumps(record)
                    first = False
    if fmt != "csv":
        yield "]"


def alert_export_stream(statement: Any, *, fmt: str, max_rows: int) -> Iterator[str]:
    from app.services.alert_service import to_alert

    first = True
    yield _csv_line(ALERT_COLUMNS) if fmt == "csv" else "["
    offset = 0
    with get_database().session() as session:
        while offset < max_rows:
            rows = session.execute(
                statement.order_by(None)
                .order_by(Prediction.created_at.desc(), Prediction.id)
                .limit(min(1000, max_rows - offset))
                .offset(offset)
            ).all()
            if not rows:
                break
            for row in rows:
                alert = to_alert(row).model_dump()
                values = [alert[c] for c in ALERT_COLUMNS]
                if fmt == "csv":
                    yield _csv_line(values)
                else:
                    yield ("" if first else ",") + json.dumps(
                        {c: _jsonable(v) for c, v in zip(ALERT_COLUMNS, values, strict=True)}
                    )
                    first = False
            offset += len(rows)
    if fmt != "csv":
        yield "]"


def summary_report(
    session: Session, settings: Settings, *, user: User, date_from: datetime | None, date_to: datetime | None
) -> dict[str, Any]:
    labels = metrics_repo.grouped_counts(session, Prediction.predicted_label, date_from, date_to)
    bands = metrics_repo.grouped_counts(session, Prediction.risk_band, date_from, date_to)
    by_disposition = prediction_repo.alert_counts_by_status(session, date_from=date_from, date_to=date_to)
    alerts_by_status = {
        "open": by_disposition.get("unreviewed", 0),
        "investigating": by_disposition.get("needs_investigation", 0),
    }
    alerts_by_status["closed"] = sum(v for k, v in by_disposition.items() if k not in {"unreviewed", "needs_investigation"})
    models = [
        {"model_name": m.model_name, "version": m.version, "dataset_family": m.dataset_family, "status": m.status}
        for m in model_repo.list_models(session, statuses=["approved"])
    ]
    total = sum(labels.values())
    return {
        "generated_at": utcnow(),
        "generated_by": user.email,
        "window": {"date_from": date_from, "date_to": date_to},
        "totals": {
            "records": total,
            "alerts": sum(alerts_by_status.values()),
            "anomalies": metrics_repo.count_where(session, Prediction.is_anomaly.is_(True), date_from, date_to),
        },
        "label_distribution": labels,
        "risk_band_distribution": bands,
        "alerts_by_status": alerts_by_status,
        "alerts_by_disposition": by_disposition,
        "jobs": status_counts(session),
        "models": models,
        "notes": [
            "Organization-wide aggregates from completed analysis jobs.",
            "Risk bands are policy outputs, not probabilities; anomalies are not necessarily attacks.",
        ],
    }


def summary_report_csv(report: dict[str, Any]) -> str:
    lines = [_csv_line(["section", "key", "value"])]
    lines.append(_csv_line(["meta", "generated_at", report["generated_at"]]))
    lines.append(_csv_line(["meta", "generated_by", report["generated_by"]]))
    for key, value in report["window"].items():
        lines.append(_csv_line(["window", key, value]))
    for section in (
        "totals",
        "label_distribution",
        "risk_band_distribution",
        "alerts_by_status",
        "alerts_by_disposition",
        "jobs",
    ):
        for key, value in report[section].items():
            lines.append(_csv_line([section, key, value]))
    for model in report["models"]:
        lines.append(_csv_line(["approved_model", f"{model['model_name']}:{model['version']}", model["dataset_family"]]))
    return "".join(lines)
