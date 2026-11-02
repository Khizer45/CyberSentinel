"""Training-side helpers for the CyberSentinel notebooks.

This package is **never imported by the API** (enforced by backend/tests/architecture). It may fit models;
``backend/app/ml`` may not.
"""

from nb_utils.config import NotebookConfig, bootstrap, load_config

__all__ = ["NotebookConfig", "bootstrap", "load_config"]
