"""Initial CyberSentinel schema (ERD v1.0 + documented extensions).

Creates the seven operational tables in dependency order, their CHECK/UNIQUE/FK constraints, the
indexes listed in ERD section 6, and PostgreSQL triggers that make ``audit_logs`` and
``alert_reviews`` append-only.

Vocabularies are written out literally (not imported from application enums) so that this
migration remains an immutable snapshot even if the application code changes later.

Requires PostgreSQL >= 13 (``gen_random_uuid()`` is built in). Tested against PostgreSQL 16.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)
JSONB = postgresql.JSONB()


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _id() -> sa.Column:
    return sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _created_at() -> sa.Column:
    return sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()"))


def _updated_at() -> sa.Column:
    return sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()"))


ROLES = ("admin", "analyst", "viewer")
DATASET_SOURCES = ("upload", "import", "sample")
DATASET_STATUSES = ("pending", "validated", "rejected", "deleted")
MODEL_TYPES = ("classifier", "anomaly_detector", "semi_supervised", "ensemble")
MODEL_STATUSES = ("draft", "approved", "retired", "revoked")
JOB_STATUSES = ("queued", "validating", "running", "completed", "failed", "cancelled")
ANALYSIS_MODES = ("classification", "anomaly", "combined")
RISK_BANDS = ("low", "medium", "high", "critical")
DISPOSITIONS = ("true_positive", "false_positive", "benign", "duplicate", "needs_investigation")
AUDIT_OUTCOMES = ("success", "failure", "denied")


def upgrade() -> None:
    # ------------------------------------------------------------------ users
    op.create_table(
        "users",
        _id(),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", TS, nullable=True),
        sa.Column("last_login_at", TS, nullable=True),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.CheckConstraint(_in("role", ROLES), name=op.f("ck_users_role_valid")),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.CheckConstraint("failed_login_attempts >= 0", name=op.f("ck_users_failed_login_attempts_nonnegative")),
        sa.CheckConstraint("token_version >= 0", name=op.f("ck_users_token_version_nonnegative")),
    )
    op.create_index(op.f("ix_users_role_is_active"), "users", ["role", "is_active"])

    # --------------------------------------------------------- model_versions
    op.create_table(
        "model_versions",
        _id(),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("version", sa.String(60), nullable=False),
        sa.Column("model_type", sa.String(40), nullable=False),
        sa.Column("task", sa.String(30), nullable=True),
        sa.Column("dataset_family", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("artifact_sha256", sa.CHAR(64), nullable=False),
        sa.Column("preprocessing_version", sa.String(60), nullable=False),
        sa.Column("feature_schema_version", sa.String(60), nullable=False),
        sa.Column("label_map", JSONB, nullable=True),
        sa.Column("threshold_config", JSONB, nullable=True),
        sa.Column("metrics", JSONB, nullable=True),
        sa.Column("explanation_method", sa.String(40), nullable=True),
        sa.Column("probability_calibrated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("status_reason", sa.String(500), nullable=True),
        sa.Column("approved_by", UUID, nullable=True),
        sa.Column("approved_at", TS, nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_versions")),
        sa.UniqueConstraint("model_name", "version", name=op.f("uq_model_versions_model_name_version")),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], name=op.f("fk_model_versions_approved_by_users"), ondelete="RESTRICT"
        ),
        sa.CheckConstraint(_in("model_type", MODEL_TYPES), name=op.f("ck_model_versions_model_type_valid")),
        sa.CheckConstraint(_in("status", MODEL_STATUSES), name=op.f("ck_model_versions_status_valid")),
        sa.CheckConstraint(
            "length(artifact_sha256) = 64 AND artifact_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_model_versions_artifact_sha256_length"),
        ),
    )
    op.create_index(op.f("ix_model_versions_status"), "model_versions", ["status"])

    # --------------------------------------------------------------- datasets
    op.create_table(
        "datasets",
        _id(),
        sa.Column("owner_user_id", UUID, nullable=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("sha256", sa.CHAR(64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("schema_version", sa.String(40), nullable=True),
        sa.Column("has_ground_truth", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("validation_report", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("deleted_at", TS, nullable=True),
        sa.Column("deleted_by", UUID, nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name=op.f("fk_datasets_owner_user_id_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["users.id"], name=op.f("fk_datasets_deleted_by_users"), ondelete="RESTRICT"
        ),
        sa.CheckConstraint(_in("source_type", DATASET_SOURCES), name=op.f("ck_datasets_source_type_valid")),
        sa.CheckConstraint(_in("status", DATASET_STATUSES), name=op.f("ck_datasets_status_valid")),
        sa.CheckConstraint("row_count IS NULL OR row_count >= 0", name=op.f("ck_datasets_row_count_nonnegative")),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name=op.f("ck_datasets_size_bytes_nonnegative")),
        sa.CheckConstraint(
            "sha256 IS NULL OR (length(sha256) = 64 AND sha256 ~ '^[0-9a-f]{64}$')",
            name=op.f("ck_datasets_sha256_length"),
        ),
        sa.CheckConstraint(
            "owner_user_id IS NOT NULL OR source_type <> 'upload'",
            name=op.f("ck_datasets_owner_required_for_upload"),
        ),
    )
    op.create_index(
        op.f("ix_datasets_owner_user_id_created_at"), "datasets", ["owner_user_id", sa.text("created_at DESC")]
    )
    op.create_index(
        op.f("ix_datasets_sha256"), "datasets", ["sha256"], postgresql_where=sa.text("sha256 IS NOT NULL")
    )
    op.create_index(op.f("ix_datasets_status"), "datasets", ["status"])

    # ---------------------------------------------------------- analysis_jobs
    op.create_table(
        "analysis_jobs",
        _id(),
        sa.Column("dataset_id", UUID, nullable=False),
        sa.Column("submitted_by", UUID, nullable=False),
        sa.Column("model_version_id", UUID, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("requested_mode", sa.String(30), nullable=False),
        sa.Column("input_rows", sa.BigInteger(), nullable=True),
        sa.Column("processed_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("summary", JSONB, nullable=True),
        sa.Column("risk_policy_version", sa.String(40), nullable=False),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("started_at", TS, nullable=True),
        sa.Column("completed_at", TS, nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_jobs")),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_analysis_jobs_dataset_id_datasets"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"], ["users.id"], name=op.f("fk_analysis_jobs_submitted_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name=op.f("fk_analysis_jobs_model_version_id_model_versions"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("status", JOB_STATUSES), name=op.f("ck_analysis_jobs_status_valid")),
        sa.CheckConstraint(
            _in("requested_mode", ANALYSIS_MODES), name=op.f("ck_analysis_jobs_requested_mode_valid")
        ),
        sa.CheckConstraint("input_rows IS NULL OR input_rows >= 0", name=op.f("ck_analysis_jobs_input_rows_nonnegative")),
        sa.CheckConstraint("processed_rows >= 0", name=op.f("ck_analysis_jobs_processed_rows_nonnegative")),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_analysis_jobs_completed_after_started"),
        ),
    )
    op.create_index(
        op.f("ix_analysis_jobs_submitted_by_created_at"),
        "analysis_jobs",
        ["submitted_by", sa.text("created_at DESC")],
    )
    op.create_index(
        op.f("ix_analysis_jobs_status_created_at"), "analysis_jobs", ["status", sa.text("created_at DESC")]
    )
    op.create_index(op.f("ix_analysis_jobs_dataset_id"), "analysis_jobs", ["dataset_id"])
    op.create_index(op.f("ix_analysis_jobs_model_version_id"), "analysis_jobs", ["model_version_id"])

    # ------------------------------------------------------------ predictions
    op.create_table(
        "predictions",
        _id(),
        sa.Column("analysis_job_id", UUID, nullable=False),
        sa.Column("record_index", sa.BigInteger(), nullable=False),
        sa.Column("predicted_label", sa.String(100), nullable=False),
        sa.Column("probability", sa.Numeric(8, 7), nullable=True),
        sa.Column("classifier_score", sa.Numeric(8, 7), nullable=True),
        sa.Column("anomaly_score", sa.Numeric(12, 8), nullable=True),
        sa.Column("is_anomaly", sa.Boolean(), nullable=True),
        sa.Column("risk_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("risk_band", sa.String(20), nullable=True),
        sa.Column("is_alert", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("true_label", sa.String(100), nullable=True),
        sa.Column("explanation", JSONB, nullable=True),
        sa.Column("flow_context", JSONB, nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_predictions")),
        sa.UniqueConstraint(
            "analysis_job_id", "record_index", name=op.f("uq_predictions_analysis_job_id_record_index")
        ),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name=op.f("fk_predictions_analysis_job_id_analysis_jobs"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_in("risk_band", RISK_BANDS), name=op.f("ck_predictions_risk_band_valid")),
        sa.CheckConstraint("record_index >= 0", name=op.f("ck_predictions_record_index_nonnegative")),
        sa.CheckConstraint(
            "probability IS NULL OR (probability >= 0 AND probability <= 1)",
            name=op.f("ck_predictions_probability_range"),
        ),
        sa.CheckConstraint(
            "classifier_score IS NULL OR (classifier_score >= 0 AND classifier_score <= 1)",
            name=op.f("ck_predictions_classifier_score_range"),
        ),
        sa.CheckConstraint(
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)",
            name=op.f("ck_predictions_risk_score_range"),
        ),
    )
    op.create_index(
        op.f("ix_predictions_analysis_job_id_risk_band"), "predictions", ["analysis_job_id", "risk_band"]
    )
    op.create_index(op.f("ix_predictions_predicted_label"), "predictions", ["predicted_label"])
    op.create_index(
        op.f("ix_predictions_alerts_created_at"),
        "predictions",
        [sa.text("created_at DESC")],
        postgresql_where=sa.text("is_alert"),
    )
    op.create_index(op.f("ix_predictions_created_at"), "predictions", ["created_at"])

    # ---------------------------------------------------------- alert_reviews
    op.create_table(
        "alert_reviews",
        _id(),
        sa.Column("prediction_id", UUID, nullable=False),
        sa.Column("reviewed_by", UUID, nullable=False),
        sa.Column("disposition", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_reviews")),
        sa.ForeignKeyConstraint(
            ["prediction_id"],
            ["predictions.id"],
            name=op.f("fk_alert_reviews_prediction_id_predictions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name=op.f("fk_alert_reviews_reviewed_by_users"), ondelete="RESTRICT"
        ),
        sa.CheckConstraint(_in("disposition", DISPOSITIONS), name=op.f("ck_alert_reviews_disposition_valid")),
        sa.CheckConstraint("notes IS NULL OR length(notes) <= 2000", name=op.f("ck_alert_reviews_notes_length")),
    )
    op.create_index(
        op.f("ix_alert_reviews_prediction_id_created_at"),
        "alert_reviews",
        ["prediction_id", sa.text("created_at DESC")],
    )
    op.create_index(op.f("ix_alert_reviews_reviewed_by"), "alert_reviews", ["reviewed_by"])

    # ------------------------------------------------------------- audit_logs
    op.create_table(
        "audit_logs",
        _id(),
        sa.Column("actor_user_id", UUID, nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(60), nullable=True),
        sa.Column("resource_id", UUID, nullable=True),
        sa.Column("request_id", sa.String(80), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False, server_default="success"),
        sa.Column("details", JSONB, nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_audit_logs_actor_user_id_users"), ondelete="RESTRICT"
        ),
        sa.CheckConstraint(_in("outcome", AUDIT_OUTCOMES), name=op.f("ck_audit_logs_outcome_valid")),
    )
    op.create_index(
        op.f("ix_audit_logs_actor_user_id_created_at"), "audit_logs", ["actor_user_id", sa.text("created_at DESC")]
    )
    op.create_index(op.f("ix_audit_logs_action_created_at"), "audit_logs", ["action", sa.text("created_at DESC")])
    op.create_index(op.f("ix_audit_logs_resource"), "audit_logs", ["resource_type", "resource_id"])
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", [sa.text("created_at DESC")])

    # ------------------------------------------- append-only enforcement (PG)
    if op.get_context().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION cybersentinel_reject_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'table % is append-only: % is not permitted', TG_TABLE_NAME, TG_OP
                    USING ERRCODE = 'insufficient_privilege';
            END;
            $$;
            """
        )
        for table in ("audit_logs", "alert_reviews"):
            op.execute(
                f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION cybersentinel_reject_mutation();"
            )
            op.execute(
                f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
                "FOR EACH STATEMENT EXECUTE FUNCTION cybersentinel_reject_mutation();"
            )


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        for table in ("alert_reviews", "audit_logs"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table};")
            op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
        op.execute("DROP FUNCTION IF EXISTS cybersentinel_reject_mutation();")
    for table in ("audit_logs", "alert_reviews", "predictions", "analysis_jobs", "datasets", "model_versions", "users"):
        op.drop_table(table)
