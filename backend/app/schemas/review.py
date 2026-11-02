from pydantic import Field

from app.core.constants import Disposition
from app.models.alert_review import REVIEW_NOTES_MAX_LENGTH
from app.schemas.common import RequestModel


class ReviewCreate(RequestModel):
    disposition: Disposition
    notes: str | None = Field(default=None, max_length=REVIEW_NOTES_MAX_LENGTH)
