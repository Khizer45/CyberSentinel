"""Pure, picklable transforms referenced from inside fitted preprocessing pipelines.

Fitted ``FunctionTransformer`` objects store a *reference* to their function (module + name). Keeping the
functions here — inside the backend package that both the notebooks and the API import — guarantees that
an exported preprocessor can be unpickled by the API and behaves identically (ML-02).

Only functions listed in :data:`ALLOWED_TRANSFORM_FUNCTIONS` are accepted by the artifact loader.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


def signed_log1p(values: ArrayLike) -> NDArray[np.float64]:
    """``sign(x) * log1p(|x|)``: compresses heavy-tailed byte/packet rates while keeping the sign.

    CIC-IDS2017 contains negative values (e.g. ``init_win_bytes_forward = -1``), so plain ``log1p`` is unsafe.
    """
    array = np.asarray(values, dtype=np.float64)
    return np.sign(array) * np.log1p(np.abs(array))


ALLOWED_TRANSFORM_FUNCTIONS = frozenset(
    {
        "app.ml.preprocessing.transforms.signed_log1p",
        "numpy.log1p",
    }
)
