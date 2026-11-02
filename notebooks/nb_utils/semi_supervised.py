"""Label-budget masking for semi-supervised experiments (ML-06).

``make_label_mask`` hides labels by replacing them with ``-1`` (scikit-learn's "unlabeled" marker). The
fitting code only ever receives the masked vector; the true labels of masked points are used **after**
fitting, for transductive evaluation only.
"""

from __future__ import annotations

import numpy as np

UNLABELED = -1


def make_label_mask(y: np.ndarray, budget: float, seed: int, *, min_per_class: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(y_masked, labeled_mask)``.

    The budget is applied per class (stratified) with at least ``min_per_class`` labeled examples for every
    class present in ``y``, so rare classes are not silently excluded at small budgets.
    """
    if not 0 < budget <= 1:
        raise ValueError("budget must be in (0, 1]")
    y = np.asarray(y)
    rng = np.random.default_rng(seed)
    labeled = np.zeros(len(y), dtype=bool)
    for cls in np.unique(y):
        idx = np.nonzero(y == cls)[0]
        take = min(len(idx), max(min_per_class, int(round(budget * len(idx)))))
        labeled[rng.choice(idx, size=take, replace=False)] = True
    y_masked = np.where(labeled, y, UNLABELED)
    assert np.array_equal(y_masked[labeled], y[labeled])
    assert np.all(y_masked[~labeled] == UNLABELED)
    return y_masked, labeled
