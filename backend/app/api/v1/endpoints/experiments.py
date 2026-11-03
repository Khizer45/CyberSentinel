"""Read-only experiment results exported by the notebooks (PRD Model Lab)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AnyUser, Experiments
from app.ml.evaluation.experiment_record import ExperimentRecord
from app.schemas.common import ERROR_RESPONSES
from app.schemas.experiment import ExperimentSummary

router = APIRouter(prefix="/experiments", tags=["experiments"], responses=ERROR_RESPONSES)


@router.get("", response_model=list[ExperimentSummary])
def list_experiments(
    user: AnyUser,
    store: Experiments,
    dataset_family: Annotated[str | None, Query(max_length=40)] = None,
    experiment_type: Annotated[str | None, Query(max_length=60)] = None,
) -> list[ExperimentSummary]:
    return store.list(dataset_family=dataset_family, experiment_type=experiment_type)


@router.get("/{experiment_id}", response_model=ExperimentRecord)
def get_experiment(experiment_id: str, user: AnyUser, store: Experiments) -> ExperimentRecord:
    return store.get(experiment_id)
