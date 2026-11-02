"""Local explanations: native XGBoost TreeSHAP, tree-path attribution, baseline deviation, reason codes."""

from app.ml.explain.explainer import explain_rows, resolve_method

__all__ = ["explain_rows", "resolve_method"]
