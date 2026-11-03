"""Supported dataset feature schemas (shown on the upload page)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AnyUser
from app.ml.datasets import list_schemas
from app.schemas.dataset import DatasetSchemaRead, FeatureSpecRead

router = APIRouter(prefix="/dataset-schemas", tags=["datasets"])


@router.get("", response_model=list[DatasetSchemaRead])
def get_schemas(user: AnyUser) -> list[DatasetSchemaRead]:
    return [
        DatasetSchemaRead(
            schema_version=s.schema_version,
            family=s.family.value,
            display_name=s.display_name,
            source=s.source,
            features=[FeatureSpecRead(name=f.name, dtype=f.dtype, description=f.description) for f in s.features],
            label_columns=list(s.label_columns),
            identifier_columns=list(s.identifier_columns),
            notes=list(s.notes),
        )
        for s in list_schemas()
    ]
