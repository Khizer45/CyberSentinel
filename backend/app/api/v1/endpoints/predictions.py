"""Prediction detail and analyst reviews (FR-13, FR-14, FR-15)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import AnalystUser, ClientIP, DbSession
from app.models import AlertReview
from app.repositories import predictions as prediction_repo
from app.schemas.common import ERROR_RESPONSES
from app.schemas.prediction import PredictionDetail, ReviewRead
from app.schemas.review import ReviewCreate
from app.services import prediction_service, review_service

router = APIRouter(prefix="/predictions", tags=["predictions"], responses=ERROR_RESPONSES)


@router.get("/{prediction_id}", response_model=PredictionDetail)
def get_prediction(prediction_id: uuid.UUID, user: AnalystUser, db: DbSession) -> PredictionDetail:
    prediction, job = prediction_service.get_visible(db, user, prediction_id)
    return prediction_service.build_detail(db, prediction, job)


@router.get("/{prediction_id}/reviews", response_model=list[ReviewRead])
def list_reviews(prediction_id: uuid.UUID, user: AnalystUser, db: DbSession) -> list[AlertReview]:
    prediction, _job = prediction_service.get_visible(db, user, prediction_id)
    return list(prediction_repo.reviews_for(db, prediction.id))


@router.post("/{prediction_id}/reviews", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
def add_review(prediction_id: uuid.UUID, payload: ReviewCreate, user: AnalystUser, db: DbSession, ip: ClientIP) -> AlertReview:
    """Append a disposition; earlier reviews are never modified (append-only history)."""
    return review_service.add_review(db, user=user, prediction_id=prediction_id, payload=payload, ip=ip)
