"""Bounded background execution of analysis jobs (FR-07..FR-10, NFR-02, SEC-08).

Design (SAD 13 open decision → resolved):

* Jobs are persisted in PostgreSQL (``status='queued'``) and executed by an in-process thread pool of
  ``JOB_WORKERS`` threads; at most ``JOB_QUEUE_MAX`` jobs are queued or running per process.
* A worker claims a job with an atomic compare-and-set (``queued → validating``), so a job runs once even if
  several API processes share the database.
* The dataset is streamed in chunks of ``INFERENCE_BATCH_SIZE`` rows; each chunk is scored, risk-scored,
  partially explained and bulk-inserted in its own transaction, which also refreshes the heartbeat
  (``updated_at``) and checks for cancellation.
* Results are all-or-nothing: failed or cancelled jobs have their partial predictions removed, so no partial
  result is ever presented as complete.
* A maintenance thread fails jobs whose heartbeat is older than ``JOB_STALE_AFTER_SECONDS`` (crashed worker)
  and dispatches queued jobs when capacity frees up.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import numpy as np
from sqlalchemy import insert, update

from app.core.config import Settings
from app.core.constants import AuditAction, AuditOutcome, DatasetStatus, JobStatus
from app.core.context import job_id_var
from app.core.errors import AppError
from app.db.session import Database
from app.db.types import utcnow
from app.ml.constants import BENIGN_LABEL, MALICIOUS_LABEL, NEEDS_REVIEW_LABEL, UNCLASSIFIED_LABEL, ClassifierTask
from app.ml.datasets import get_schema
from app.ml.errors import LabelNormalizationError, MLError
from app.ml.evaluation.metrics import StreamingConfusion, counts_to_rates
from app.ml.inference import InferenceEngine, InferenceOutput
from app.ml.preprocessing import CleaningStats, context_frame, inspect_csv, iter_canonical_chunks, normalize_labels
from app.ml.risk import RiskResult
from app.models import AnalysisJob, Prediction
from app.repositories import analysis_jobs as job_repo
from app.repositories import predictions as prediction_repo
from app.services import audit_service
from app.services.explanation_service import explain, select_positions
from app.services.model_registry_service import ModelRegistry
from app.services.preprocessing_adapter import build_flow_contexts
from app.services.risk_scoring_service import RiskScoringService
from app.services.storage_service import UploadStorage

logger = logging.getLogger("cybersentinel.jobs")
NON_MALICIOUS = {BENIGN_LABEL, NEEDS_REVIEW_LABEL, UNCLASSIFIED_LABEL}
MAINTENANCE_INTERVAL_SECONDS = 30


class JobFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class JobCancelled(Exception):
    pass


def _round(value: Any, digits: int) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if not np.isfinite(number) else round(number, digits)


class SummaryAccumulator:
    """Bounded aggregate statistics for ``analysis_jobs.summary`` (no per-row data)."""

    def __init__(self, *, classes: list[str] | None, task: str | None, policy_version: str) -> None:
        self.classes = classes
        self.task = task
        self.policy_version = policy_version
        self.rows = 0
        self.labels: Counter[str] = Counter()
        self.bands: Counter[str] = Counter()
        self.anomalies: int | None = None
        self.alerts = 0
        self.needs_review = 0
        self.explained = 0
        self.risk_histogram = np.zeros(101, dtype=np.int64)
        self.risk_sum = 0.0
        self.risk_max = 0.0
        self.quality = CleaningStats()
        self.confusion = StreamingConfusion()
        self.anomaly_counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
        self.labeled_rows = 0

    def update(
        self,
        out: InferenceOutput,
        risk: RiskResult,
        stats: CleaningStats,
        truth_model_space: list[str] | None,
        truth_binary: np.ndarray | None,
        explained: int,
    ) -> None:
        self.rows += out.size
        self.labels.update(str(v) for v in out.predicted_label)
        self.bands.update(str(v) for v in risk.band)
        self.alerts += int(risk.is_alert.sum())
        self.needs_review += int(out.needs_review.sum())
        self.explained += explained
        if out.is_anomaly is not None:
            self.anomalies = (self.anomalies or 0) + int(out.is_anomaly.sum())
        self.risk_histogram += np.bincount(np.clip(np.floor(risk.score).astype(int), 0, 100), minlength=101)
        self.risk_sum += float(risk.score.sum())
        self.risk_max = max(self.risk_max, float(risk.score.max(initial=0.0)))
        self.quality.merge(stats)
        if truth_binary is not None:
            self.labeled_rows += len(truth_binary)
            if truth_model_space is not None and out.top_label is not None:
                self.confusion.update(truth_model_space, [str(v) for v in out.top_label])
            if out.is_anomaly is not None:
                flagged = out.is_anomaly.astype(int)
                self.anomaly_counts["tp"] += int(((truth_binary == 1) & (flagged == 1)).sum())
                self.anomaly_counts["fp"] += int(((truth_binary == 0) & (flagged == 1)).sum())
                self.anomaly_counts["tn"] += int(((truth_binary == 0) & (flagged == 0)).sum())
                self.anomaly_counts["fn"] += int(((truth_binary == 1) & (flagged == 0)).sum())

    def _percentile(self, q: float) -> float | None:
        total = int(self.risk_histogram.sum())
        if total == 0:
            return None
        index = int(np.searchsorted(np.cumsum(self.risk_histogram), q * total, side="left"))
        return float(min(index, 100))

    def to_dict(self, *, model: dict[str, Any], duration: float) -> dict[str, Any]:
        evaluation = None
        if self.labeled_rows:
            evaluation = {
                "source": (
                    "ground-truth labels contained in the uploaded dataset (used for evaluation only, never as model input)"
                ),
                "labeled_rows": self.labeled_rows,
                "classification": self.confusion.report(BENIGN_LABEL),
                "anomaly_detection": counts_to_rates(**self.anomaly_counts) if self.anomalies is not None else None,
                "note": "Classification metrics use the classifier's top class before needs_review abstention.",
            }
        malicious = sum(n for label, n in self.labels.items() if label not in NON_MALICIOUS)
        return {
            "rows": {"processed": self.rows},
            "label_counts": dict(self.labels.most_common(50)),
            "risk_band_counts": dict(self.bands),
            "malicious_count": malicious,
            "benign_count": self.labels.get(BENIGN_LABEL, 0),
            "needs_review_count": self.labels.get(NEEDS_REVIEW_LABEL, 0),
            "anomaly_count": self.anomalies,
            "alert_count": self.alerts,
            "explained_rows": self.explained,
            "risk_score": {
                "mean": round(self.risk_sum / self.rows, 2) if self.rows else None,
                "p50": self._percentile(0.5),
                "p95": self._percentile(0.95),
                "max": round(self.risk_max, 2) if self.rows else None,
            },
            "data_quality": {
                "non_finite_values": sum(self.quality.non_finite.values()),
                "non_numeric_values": sum(self.quality.non_numeric.values()),
                "out_of_range_values": sum(self.quality.out_of_range.values()),
                "missing_values": sum(self.quality.missing.values()),
            },
            "evaluation": evaluation,
            "risk_policy_version": self.policy_version,
            "model": model,
            "timing": {
                "duration_seconds": round(duration, 3),
                "rows_per_second": round(self.rows / duration, 1) if duration > 0 else None,
            },
        }


class JobRunner:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        registry: ModelRegistry,
        risk: RiskScoringService,
        storage: UploadStorage,
        *,
        inline: bool = False,
    ) -> None:
        self.database = database
        self.settings = settings
        self.registry = registry
        self.risk = risk
        self.storage = storage
        self.inline = inline
        self._executor = None if inline else ThreadPoolExecutor(max_workers=settings.job_workers, thread_name_prefix="cs-job")
        self._active: set[uuid.UUID] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._maintenance: threading.Thread | None = None
        key = settings.ip_pseudonymization_key
        self.ip_key = key.get_secret_value().encode() if key else None

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self.recover_stale()
        if not self.inline:
            self._maintenance = threading.Thread(target=self._maintenance_loop, name="cs-job-maintenance", daemon=True)
            self._maintenance.start()
            self.dispatch_queued()

    def shutdown(self) -> None:
        self._stop.set()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

    @property
    def running(self) -> bool:
        return not self._stop.is_set()

    def _maintenance_loop(self) -> None:
        while not self._stop.wait(MAINTENANCE_INTERVAL_SECONDS):
            try:
                self.recover_stale()
                self.dispatch_queued()
            except Exception:  # pragma: no cover - keep the loop alive
                logger.exception("job maintenance failed")

    def has_capacity(self) -> bool:
        with self._lock:
            return len(self._active) < self.settings.job_queue_max

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def submit(self, job_id: uuid.UUID) -> bool:
        with self._lock:
            if job_id in self._active:
                return True
            if len(self._active) >= self.settings.job_queue_max:
                return False
            self._active.add(job_id)
        if self.inline or self._executor is None:
            self._run(job_id)
        else:
            self._executor.submit(self._run, job_id)
        return True

    def _run(self, job_id: uuid.UUID) -> None:
        try:
            self.process(job_id)
        except Exception:  # pragma: no cover - process() handles its own errors
            logger.exception("unexpected job runner failure")
        finally:
            with self._lock:
                self._active.discard(job_id)

    def dispatch_queued(self) -> None:
        with self.database.session() as session:
            ids = job_repo.queued_ids(session, self.settings.job_queue_max)
        for job_id in ids:
            if not self.submit(job_id):
                break

    def recover_stale(self) -> None:
        cutoff = utcnow() - timedelta(seconds=self.settings.job_stale_after_seconds)
        with self.database.session() as session:
            stale = job_repo.stale_running(session, cutoff)
        for job_id in stale:
            with self._lock:
                if job_id in self._active:
                    continue
            self._fail(
                job_id, "worker_interrupted", "The worker processing this job stopped unexpectedly. Submit the analysis again."
            )

    # ------------------------------------------------------------------ execution
    def process(self, job_id: uuid.UUID) -> None:
        token = job_id_var.set(str(job_id))
        try:
            with self.database.session() as session:
                if not job_repo.transition(
                    session, job_id, [JobStatus.QUEUED.value], JobStatus.VALIDATING.value, started_at=utcnow()
                ):
                    session.rollback()
                    return
                session.commit()
                job = session.get(AnalysisJob, job_id)
                assert job is not None
                try:
                    self._execute(session, job)
                except JobCancelled:
                    session.rollback()
                    self._cleanup_cancelled(job_id)
                except JobFailure as exc:
                    session.rollback()
                    self._fail(job_id, exc.code, exc.message)
                except AppError as exc:
                    session.rollback()
                    self._fail(job_id, exc.code, exc.message)
                except MLError as exc:
                    session.rollback()
                    self._fail(job_id, exc.code, exc.message)
                except Exception:
                    session.rollback()
                    logger.exception("analysis job failed unexpectedly")
                    self._fail(job_id, "internal_error", "An unexpected error occurred while processing the job.")
        finally:
            job_id_var.reset(token)

    def _execute(self, session: Any, job: AnalysisJob) -> None:
        started = time.perf_counter()
        dataset, model = job.dataset, job.model_version
        if dataset.status != DatasetStatus.VALIDATED or not dataset.storage_key:
            raise JobFailure("dataset_unavailable", "The dataset is no longer available.")
        if self.storage.sha256(dataset.storage_key) != dataset.sha256:
            raise JobFailure("dataset_integrity_failed", "The stored dataset failed checksum verification.")
        if dataset.schema_version != model.feature_schema_version:
            raise JobFailure("incompatible_dataset", "The dataset schema does not match the model's feature schema.")
        bundle = self.registry.get_bundle(model)
        engine = InferenceEngine(bundle)
        mode = engine.check_mode(job.requested_mode)
        schema = get_schema(dataset.schema_version)  # type: ignore[arg-type]
        path = self.storage.path_for(dataset.storage_key)
        layout = inspect_csv(path, schema, required_features=engine.input_features)
        if not job_repo.transition(session, job.id, [JobStatus.VALIDATING.value], JobStatus.RUNNING.value):
            raise JobCancelled()
        session.commit()

        clf = bundle.manifest.components.classifier
        classes = clf.classes if clf else None
        task = clf.task.value if clf else None
        summary = SummaryAccumulator(classes=classes, task=task, policy_version=self.risk.version)
        budget = self.settings.explain_max_rows_per_job
        scope = self.settings.explain_scope
        processed = 0
        for chunk in iter_canonical_chunks(
            path, layout, schema, chunk_size=self.settings.inference_batch_size, max_rows=self.settings.max_upload_rows
        ):
            if job_repo.current_status(session, job.id) != JobStatus.RUNNING:
                raise JobCancelled()
            output = engine.predict(chunk.features, mode, keep_transformed=scope != "none" and budget > 0)
            risk = self.risk.score(bundle, output)
            positions = select_positions(scope, output, risk, budget)
            explanations: dict[int, dict[str, Any]] = {}
            if positions:
                explanations = explain(
                    bundle,
                    engine.prepare(chunk.features),
                    output,
                    positions,
                    risk,
                    self.risk.policy,
                    top_k=self.settings.explain_top_k,
                )
                budget -= len(positions)

            truth_store, truth_model, truth_binary = self._ground_truth(chunk, schema, dataset.has_ground_truth, task)
            contexts = build_flow_contexts(context_frame(chunk, schema), schema, self.ip_key)
            rows = []
            for i in range(output.size):
                rows.append(
                    {
                        "analysis_job_id": job.id,
                        "record_index": int(chunk.start_index + i),
                        "predicted_label": str(output.predicted_label[i])[:100],
                        "probability": _round(output.probability[i], 7) if output.probability is not None else None,
                        "classifier_score": _round(output.classifier_score[i], 7)
                        if output.classifier_score is not None
                        else None,
                        "anomaly_score": _round(output.anomaly_score[i], 8) if output.anomaly_score is not None else None,
                        "is_anomaly": bool(output.is_anomaly[i]) if output.is_anomaly is not None else None,
                        "risk_score": float(risk.score[i]),
                        "risk_band": str(risk.band[i]),
                        "is_alert": bool(risk.is_alert[i]),
                        "true_label": truth_store[i] if truth_store is not None else None,
                        "explanation": explanations.get(i),
                        "flow_context": contexts[i] if contexts else None,
                    }
                )
            if rows:
                session.execute(insert(Prediction), rows)
            processed += output.size
            session.execute(
                update(AnalysisJob)
                .where(AnalysisJob.id == job.id)
                .values(processed_rows=processed, updated_at=utcnow())
                .execution_options(synchronize_session=False)
            )
            session.commit()
            summary.update(output, risk, chunk.stats, truth_model, truth_binary, len(positions))

        model_info = {
            "id": str(model.id),
            "name": model.model_name,
            "version": model.version,
            "manifest_sha256": model.artifact_sha256,
        }
        if not job_repo.transition(
            session,
            job.id,
            [JobStatus.RUNNING.value],
            JobStatus.COMPLETED.value,
            completed_at=utcnow(),
            processed_rows=processed,
            input_rows=processed,
            summary=summary.to_dict(model=model_info, duration=time.perf_counter() - started),
        ):
            raise JobCancelled()
        audit_service.record(
            session,
            AuditAction.ANALYSIS_COMPLETE,
            actor_id=job.submitted_by,
            resource_type="analysis_job",
            resource_id=job.id,
            details={
                "rows": processed,
                "alerts": summary.alerts,
                "model": model.model_name,
                "version": model.version,
                "risk_policy_version": self.risk.version,
            },
        )
        session.commit()
        logger.info("analysis job completed", extra={"rows": processed, "alerts": summary.alerts})

    @staticmethod
    def _ground_truth(
        chunk: Any, schema: Any, enabled: bool, task: str | None
    ) -> tuple[list[str] | None, list[str] | None, np.ndarray | None]:
        """Ground truth for evaluation only. Returns (value stored in true_label, label in model space, binary)."""
        if not enabled or chunk.labels is None:
            return None, None, None
        try:
            labels = normalize_labels(chunk.labels, schema)
        except LabelNormalizationError:
            return None, None, None
        binary = labels.binary.to_numpy(dtype=int)
        binary_names = [MALICIOUS_LABEL if b else BENIGN_LABEL for b in binary]
        stored = [str(v) for v in labels.category] if labels.category is not None else binary_names
        if task == ClassifierTask.BINARY.value:
            model_space = binary_names
        elif task is not None and labels.category is not None:
            model_space = stored
        else:
            model_space = None
        return stored, model_space, binary

    # ------------------------------------------------------------------ failure paths
    def _cleanup_cancelled(self, job_id: uuid.UUID) -> None:
        with self.database.session() as session:
            removed = prediction_repo.delete_for_job(session, job_id)
            session.commit()
        logger.info("analysis job cancelled; partial results removed", extra={"removed_rows": removed})

    def _fail(self, job_id: uuid.UUID, code: str, message: str) -> None:
        with self.database.session() as session:
            prediction_repo.delete_for_job(session, job_id)
            job = session.get(AnalysisJob, job_id)
            changed = job_repo.transition(
                session,
                job_id,
                [JobStatus.QUEUED.value, JobStatus.VALIDATING.value, JobStatus.RUNNING.value],
                JobStatus.FAILED.value,
                error_code=code[:60],
                error_message=message[:500],
                completed_at=utcnow(),
                processed_rows=0,
            )
            if changed and job is not None:
                audit_service.record(
                    session,
                    AuditAction.ANALYSIS_FAIL,
                    actor_id=job.submitted_by,
                    outcome=AuditOutcome.FAILURE,
                    resource_type="analysis_job",
                    resource_id=job_id,
                    details={"error_code": code},
                )
            session.commit()
        logger.warning("analysis job failed", extra={"error_code": code})
