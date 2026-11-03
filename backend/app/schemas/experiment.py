from datetime import datetime

from pydantic import BaseModel


class ExperimentSummary(BaseModel):
    experiment_id: str
    experiment_type: str
    title: str
    dataset_family: str
    schema_version: str
    created_at: datetime
    row_count: int
