# model_artifacts — trusted model bundles (MODEL_DIR)

This directory is the **trusted, read-only** model location for the API (`MODEL_DIR`). It is populated only by
`notebooks/06_model_evaluation.ipynb` on your machine. The backend never trains, tunes or downloads models, and
there is no upload endpoint for models.

```
model_artifacts/
├── registry.json                       # MODEL_MANIFEST: index of exported bundles (tracked in git; starts empty)
├── bundles/<model_name>/<version>/     # git-ignored binaries
│   ├── manifest.json                   # validated contract (schema 1.0): hashes, features, thresholds, metrics, runtime
│   ├── preprocessor.joblib             # fitted ColumnTransformer
│   ├── classifier.joblib               # optional (multi-class or binary, predict_proba, classes 0..K-1)
│   ├── anomaly_detector.joblib         # optional (IsolationForest)
│   ├── golden_input.csv / golden_expected.json   # train/serve parity fixtures
│   └── model_card.md
├── experiments/*.json                  # notebook-exported experiment results (served read-only by /api/v1/experiments)
└── staging/                            # notebook intermediates (git-ignored, never loaded by the API)
```

## Chain of trust

1. `registry.json` lists each bundle with the SHA-256 of its `manifest.json`.
2. `python -m app.cli models sync` validates each listed bundle (manifest schema, per-file SHA-256, runtime
   compatibility, class allowlist, interface checks, golden parity) and registers it in PostgreSQL as **draft**,
   pinning the manifest hash in `model_versions.artifact_sha256`.
3. An administrator approves a version (`python -m app.cli models approve <name> <version>` or the Models page).
4. At inference the API re-verifies the pinned hash and every file hash before `joblib.load`. Any mismatch,
   missing file or incompatible library version makes the model unavailable (HTTP 503) instead of guessing.

**Security:** joblib/pickle files execute code when loaded. Only place files here that were produced by your own
notebook run. Keep this directory writable only by the person/process that exports models.

See `docs/model_artifact_integration_guide.md` for the full contract and `docs/model_training_guide.md` for training.
