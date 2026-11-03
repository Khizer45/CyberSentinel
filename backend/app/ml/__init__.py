"""Runtime-safe machine-learning library shared by the API and the training notebooks.

Rules enforced by ``tests/architecture``:

* No estimator is ever fitted here (no ``fit`` / ``fit_transform`` / ``partial_fit`` calls).
* No network access (no HTTP clients, no model downloads).
* ``joblib.load`` is only called from :mod:`app.ml.artifacts.loader` after integrity checks.
* ``joblib.dump`` is only called from :mod:`app.ml.artifacts.export`, which the notebooks use
  to package models they trained themselves.

This package must not import application configuration (``app.core.config``) or the database layer,
so that notebooks can import it without a running backend.
"""
