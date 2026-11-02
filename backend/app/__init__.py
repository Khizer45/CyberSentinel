"""CyberSentinel backend package.

Importing this package has no side effects: configuration, database connections and
model artifacts are only touched when the application factory (``app.main``) or the CLI runs.
The ``app.ml`` sub-package is intentionally importable on its own so that the training
notebooks reuse the exact preprocessing code that the API uses at inference time.
"""

__version__ = "1.0.0"
