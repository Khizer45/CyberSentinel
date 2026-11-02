"""Build (unfitted) preprocessing pipelines and benign reference statistics.

The pipeline only uses scikit-learn built-ins plus :func:`app.ml.preprocessing.transforms.signed_log1p`,
which the API's artifact loader allowlists. It is fitted on the **training split only** (notebook 02).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from app.ml.artifacts.manifest import FeatureReference, InputFeature
from app.ml.datasets import DatasetSchema
from app.ml.preprocessing.transforms import signed_log1p

PREPROCESSING_STEPS = [
    "numeric: median imputation (fitted on train)",
    "numeric: signed log1p compression of heavy-tailed values",
    "numeric: standardization (fitted on train)",
    "categorical: constant 'missing' imputation",
    "categorical: one-hot encoding, unseen/infrequent categories mapped to an 'infrequent' bucket",
]


def build_preprocessor(input_features: list[InputFeature], *, min_category_frequency: int = 20) -> ColumnTransformer:
    numeric = [f.name for f in input_features if f.dtype == "numeric"]
    categorical = [f.name for f in input_features if f.dtype == "categorical"]
    transformers = []
    if numeric:
        transformers.append(
            (
                "num",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                        ("log", FunctionTransformer(signed_log1p, feature_names_out="one-to-one")),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric,
            )
        )
    if categorical:
        transformers.append(
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
                        (
                            "onehot",
                            OneHotEncoder(
                                handle_unknown="infrequent_if_exist",
                                min_frequency=min_category_frequency,
                                sparse_output=False,
                            ),
                        ),
                    ]
                ),
                categorical,
            )
        )
    return ColumnTransformer(transformers, remainder="drop", sparse_threshold=0.0, verbose_feature_names_out=True)


def input_feature_specs(schema: DatasetSchema, feature_names: list[str], train: pd.DataFrame) -> list[InputFeature]:
    specs = []
    for name in feature_names:
        dtype = schema.feature_dtype(name)
        categories = sorted(str(v) for v in train[name].dropna().unique()) if dtype == "categorical" else None
        specs.append(InputFeature(name=name, dtype=dtype, categories=categories))
    return specs


def benign_reference(train: pd.DataFrame, specs: list[InputFeature], benign_mask: pd.Series) -> dict[str, FeatureReference]:
    """Median/IQR (numeric) or mode (categorical) of benign *training* rows, used for reason codes."""
    benign = train.loc[benign_mask]
    reference: dict[str, FeatureReference] = {}
    for spec in specs:
        column = benign[spec.name].dropna()
        if column.empty:
            continue
        if spec.dtype == "numeric":
            q25, median, q75 = np.quantile(column.to_numpy(dtype=float), [0.25, 0.5, 0.75])
            reference[spec.name] = FeatureReference(median=float(median), q25=float(q25), q75=float(q75))
        else:
            counts = column.astype(str).value_counts(normalize=True)
            reference[spec.name] = FeatureReference(mode=str(counts.index[0]), mode_frequency=float(counts.iloc[0]))
    return reference
