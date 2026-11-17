"""Create a DEMO model bundle and a DEMO flow CSV so the UI can be tried without the real datasets.

The model is fitted on synthetic data by the test fixtures: its predictions and metrics are meaningless and must
never be used for real analysis. Run inside the backend container:

    docker compose exec backend python scripts/demo_setup.py

Then register and approve it:

    docker compose exec backend python -m app.cli models sync
    docker compose exec backend python -m app.cli models approve unsw-nb15-demo 1.0.0
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from tests.fixtures.bundles import build_bundle
from tests.fixtures.data import unsw_csv

MODEL_NAME = "unsw-nb15-demo"


def main() -> int:
    model_dir = get_settings().model_dir
    if (model_dir / "bundles" / MODEL_NAME / "1.0.0").exists():
        print(f"Demo bundle already exists in {model_dir}/bundles/{MODEL_NAME}/1.0.0")
    else:
        build_bundle(model_dir, family="unsw_nb15", algorithm="random_forest", model_name=MODEL_NAME)
        print(f"Demo bundle written to {model_dir}/bundles/{MODEL_NAME}/1.0.0 (synthetic data, not a real model)")
    demo_dir = model_dir / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    csv_path = demo_dir / "demo-flows.csv"
    csv_path.write_bytes(unsw_csv(rows=3000, seed=7))
    print(f"Demo CSV written to {csv_path} (model_artifacts/demo/demo-flows.csv on your computer)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
