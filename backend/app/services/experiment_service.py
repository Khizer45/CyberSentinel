"""Read-only access to experiment results exported by the notebooks (PRD Model Lab, UC4).

The API never runs experiments; it validates and serves ``EXPERIMENTS_DIR/*.json`` files produced by
notebooks 03–06. Invalid files are skipped (and logged) rather than shown.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from app.core.errors import NotFoundError
from app.ml.evaluation.experiment_record import ExperimentRecord, read_experiment
from app.schemas.experiment import ExperimentSummary

logger = logging.getLogger("cybersentinel.experiments")
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{2,99}$")


class ExperimentStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._cache: dict[Path, tuple[float, ExperimentRecord]] = {}
        self._lock = threading.Lock()

    def _load(self, path: Path) -> ExperimentRecord | None:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        with self._lock:
            cached = self._cache.get(path)
            if cached and cached[0] == mtime:
                return cached[1]
        try:
            record = read_experiment(path)
        except Exception:  # noqa: BLE001 - invalid files are skipped, never served
            logger.warning("skipping invalid experiment file", extra={"file": path.name})
            return None
        with self._lock:
            self._cache[path] = (mtime, record)
        return record

    def list(self, *, dataset_family: str | None, experiment_type: str | None) -> list[ExperimentSummary]:
        if not self.directory.is_dir():
            return []
        summaries = []
        for path in sorted(self.directory.glob("*.json")):
            record = self._load(path)
            if record is None:
                continue
            if dataset_family and record.dataset_family != dataset_family:
                continue
            if experiment_type and record.experiment_type != experiment_type:
                continue
            summaries.append(
                ExperimentSummary(
                    experiment_id=record.experiment_id,
                    experiment_type=record.experiment_type,
                    title=record.title,
                    dataset_family=record.dataset_family,
                    schema_version=record.schema_version,
                    created_at=record.created_at,
                    row_count=len(record.rows),
                )
            )
        return sorted(summaries, key=lambda s: s.created_at, reverse=True)

    def get(self, experiment_id: str) -> ExperimentRecord:
        if not _ID.match(experiment_id):
            raise NotFoundError("Experiment not found.")
        record = self._load(self.directory / f"{experiment_id}.json")
        if record is None or record.experiment_id != experiment_id:
            raise NotFoundError("Experiment not found.")
        return record
