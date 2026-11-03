"""Operator command-line interface (run from ``backend/`` with the API's virtual environment).

    python -m app.cli create-admin --email admin@example.org --display-name "Platform Admin"
    python -m app.cli models sync | list | approve NAME VERSION | retire NAME VERSION | revoke NAME VERSION --reason TEXT
    python -m app.cli models verify NAME VERSION
    python -m app.cli datasets import --file PATH [--name NAME] [--schema-version V]
        [--source-type import|sample] [--owner-email E]
    python -m app.cli datasets purge --older-than-days N
    python -m app.cli export-openapi --output ../docs/api/openapi.json
    python -m app.cli check-config

None of these commands trains, tunes or downloads models.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.constants import AuditAction, DatasetSourceType, ModelStatus, UserRole
from app.core.security import hash_password
from app.db.session import Database, build_engine, init_database
from app.models import User
from app.repositories import model_versions as model_repo
from app.repositories import users as user_repo
from app.services import audit_service, dataset_service, model_registry_service
from app.services.auth_service import validate_new_password
from app.services.model_registry_service import ModelRegistry
from app.services.storage_service import UploadStorage
from app.utils.text import normalize_email


def _database(settings: Settings) -> Database:
    database = Database(build_engine(settings.database_url.get_secret_value(), statement_timeout_ms=None))
    init_database(database)
    return database


def _read_password(args: argparse.Namespace) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    return first


def cmd_create_admin(args: argparse.Namespace, settings: Settings) -> int:
    email = normalize_email(args.email)
    password = _read_password(args)
    validate_new_password(settings, password, email)
    with _database(settings).session() as session:
        if user_repo.get_by_email(session, email):
            print(f"A user with e-mail {email} already exists.", file=sys.stderr)
            return 1
        user = User(
            email=email,
            display_name=args.display_name[:120],
            role=UserRole.ADMIN.value,
            password_hash=hash_password(password),
            is_active=True,
        )
        session.add(user)
        session.flush()
        audit_service.record(
            session,
            AuditAction.USER_CREATE,
            actor_id=None,
            resource_type="user",
            resource_id=user.id,
            details={"role": user.role, "source": "cli"},
        )
        session.commit()
        print(f"Administrator {email} created (id {user.id}).")
    return 0


def _find_model(session, name: str, version: str):  # type: ignore[no-untyped-def]
    model = model_repo.get_by_name_version(session, name, version)
    if model is None:
        raise SystemExit(f"Model {name} {version} is not registered (run `python -m app.cli models sync`).")
    return model


def cmd_models(args: argparse.Namespace, settings: Settings) -> int:
    registry = ModelRegistry(settings)
    with _database(settings).session() as session:
        if args.action == "sync":
            results = model_registry_service.sync_from_registry(session, settings, registry)
            if not results:
                print(f"No bundles listed in {settings.model_manifest}.")
            for r in results:
                print(f"[{r.outcome:10s}] {r.model_name} {r.version}: {r.detail}")
            return 1 if any(r.outcome == "error" for r in results) else 0
        if args.action == "list":
            for m in model_repo.list_models(session, statuses=None):
                print(f"{m.model_name:45s} {m.version:12s} {m.model_type:16s} {m.status:9s} {m.feature_schema_version}")
            return 0
        model = _find_model(session, args.name, args.version)
        if args.action == "verify":
            checks = registry.verify(model)
            for check in checks:
                print(f"[{'PASS' if check['passed'] else 'FAIL'}] {check['name']}: {check.get('detail')}")
            return 0 if all(c["passed"] for c in checks) else 1
        target = {"approve": ModelStatus.APPROVED, "retire": ModelStatus.RETIRED, "revoke": ModelStatus.REVOKED}[args.action]
        updated = model_registry_service.change_status(
            session,
            registry,
            actor=None,
            model_version_id=model.id,
            new_status=target,
            reason=getattr(args, "reason", None),
            ip=None,
        )
        print(f"{updated.model_name} {updated.version} is now {updated.status}.")
    return 0


def cmd_datasets(args: argparse.Namespace, settings: Settings) -> int:
    storage = UploadStorage(settings.upload_dir)
    with _database(settings).session() as session:
        if args.action == "purge":
            count = dataset_service.purge_expired(session, settings, storage, older_than_days=args.older_than_days)
            print(f"{count} dataset file(s) purged.")
            return 0
        owner = None
        if args.owner_email:
            owner = user_repo.get_by_email(session, normalize_email(args.owner_email))
            if owner is None:
                raise SystemExit("Owner not found.")
        dataset = dataset_service.import_local_file(
            session,
            settings,
            storage,
            path=Path(args.file),
            name=args.name,
            schema_version=args.schema_version,
            owner=owner,
            source_type=DatasetSourceType(args.source_type),
        )
        print(f"Imported dataset {dataset.id} ({dataset.row_count} rows, schema {dataset.schema_version}).")
    return 0


def cmd_export_openapi(args: argparse.Namespace, settings: Settings) -> int:
    from app.main import create_app

    schema = create_app(settings).openapi()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OpenAPI schema written to {output}")
    return 0


def cmd_check_config(_args: argparse.Namespace, settings: Settings) -> int:
    print(f"environment: {settings.app_env}")
    print(f"model dir: {settings.model_dir} (exists: {settings.model_dir.is_dir()})")
    print(f"model manifest: {settings.model_manifest} (exists: {settings.model_manifest.is_file()})")  # type: ignore[union-attr]
    print(f"risk policy: {settings.risk_policy_path} (exists: {settings.risk_policy_path.is_file()})")
    print(f"upload dir: {settings.upload_dir}")
    print(f"CORS origins: {', '.join(settings.cors_origins)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="CyberSentinel operator commands")
    sub = parser.add_subparsers(dest="command", required=True)

    admin = sub.add_parser("create-admin", help="create an administrator account")
    admin.add_argument("--email", required=True)
    admin.add_argument("--display-name", required=True)
    admin.add_argument("--password-stdin", action="store_true", help="read the password from standard input")
    admin.set_defaults(func=cmd_create_admin)

    models = sub.add_parser("models", help="model registry operations")
    msub = models.add_subparsers(dest="action", required=True)
    msub.add_parser("sync", help="register bundles listed in MODEL_MANIFEST as draft")
    msub.add_parser("list", help="list registered model versions")
    for action in ("approve", "retire", "verify", "revoke"):
        p = msub.add_parser(action)
        p.add_argument("name")
        p.add_argument("version")
        if action == "revoke":
            p.add_argument("--reason", required=True)
    models.set_defaults(func=cmd_models)

    datasets = sub.add_parser("datasets", help="dataset operations")
    dsub = datasets.add_subparsers(dest="action", required=True)
    imp = dsub.add_parser("import", help="import a local CSV (validated like an upload)")
    imp.add_argument("--file", required=True)
    imp.add_argument("--name")
    imp.add_argument("--schema-version")
    imp.add_argument("--source-type", choices=["import", "sample"], default="import")
    imp.add_argument("--owner-email", help="owner; omit for a shared system dataset")
    purge = dsub.add_parser("purge", help="delete stored files of datasets older than N days")
    purge.add_argument("--older-than-days", type=int, required=True)
    datasets.set_defaults(func=cmd_datasets)

    openapi = sub.add_parser("export-openapi", help="write the OpenAPI schema to a file")
    openapi.add_argument("--output", default="../docs/api/openapi.json")
    openapi.set_defaults(func=cmd_export_openapi)

    check = sub.add_parser("check-config", help="print the resolved (non-secret) configuration")
    check.set_defaults(func=cmd_check_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args, get_settings()))


if __name__ == "__main__":
    raise SystemExit(main())
