"""Provision, harden, and verify PostgreSQL roles without handling application rows.

Run only from a trusted operator process with TWF_PG_ADMIN_URL. Passwords/URLs are
read from the environment and never printed. API containers must not receive them.
"""

import argparse
import os
import sys
from typing import Any

import psycopg
from psycopg import Cursor, sql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

REQUIRED_DELETE_TABLES = frozenset(
    {
        "broker_attempts",
        "dhan_market_data_secrets",
        "discovery_active_slots",
        "manual_order_previews",
        "mcp_oauth_attempts",
        "mcp_secrets",
        "scanner_v2_derivative_templates",
        "watchlist_activity",
        "watchlist_items",
        "watchlist_notes",
        "watchlists",
    }
)
IMMUTABLE_EVENT_TABLES = frozenset({"twf_order_events", "twf_queue_events"})
APPEND_ONLY_EVIDENCE_TABLES = frozenset({"preference_changes", "scanner_v2_runs"})
EXPECTED_HEAD = "0027_oe3_order_event_audit"


def _ident_env(name: str, default: str) -> str:
    value = os.environ.get(name, default)
    if not value or len(value) > 63 or not value.replace("_", "a").isalnum():
        raise ValueError(f"{name} must be a simple PostgreSQL identifier")
    return value


def _connection() -> psycopg.Connection:
    raw = os.environ.get("TWF_PG_ADMIN_URL")
    if not raw:
        raise ValueError("Set TWF_PG_ADMIN_URL in the operator environment")
    try:
        url = make_url(raw)
    except ArgumentError as exc:
        raise ValueError("TWF_PG_ADMIN_URL is invalid") from exc
    if url.get_backend_name() != "postgresql" or not url.database:
        raise ValueError("TWF_PG_ADMIN_URL must name a PostgreSQL database")
    return psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    )


def _row(cursor: Cursor[tuple[Any, ...]]) -> tuple[Any, ...]:
    row = cursor.fetchone()
    if row is None:
        raise ValueError("Expected PostgreSQL catalog row is missing")
    return row


def _scalar(cursor: Cursor[tuple[Any, ...]]) -> Any:
    return _row(cursor)[0]


def _role_exists(db: psycopg.Connection, name: str) -> bool:
    return bool(
        db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)).fetchone()
    )


def _require_admin(db: psycopg.Connection) -> None:
    if not _scalar(
        db.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
    ):
        raise ValueError(
            "Role cutover requires a trusted PostgreSQL superuser connection"
        )


def _require_roles(db: psycopg.Connection, migrator: str, app: str) -> None:
    if migrator == app or not _role_exists(db, migrator) or not _role_exists(db, app):
        raise ValueError("Distinct existing migrator and runtime roles are required")
    flags = _row(
        db.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
            "FROM pg_roles WHERE rolname=%s",
            (app,),
        )
    )
    if any(flags):
        raise ValueError("Runtime role has elevated PostgreSQL attributes")
    # Explicit and inherited membership can permit schema/role takeover.
    elevated = db.execute(
        "SELECT rolname FROM pg_roles WHERE rolsuper OR rolcreatedb OR "
        "rolcreaterole OR rolreplication OR rolbypassrls"
    ).fetchall()
    for target in {migrator, _scalar(db.execute("SELECT current_user"))} | {
        name for (name,) in elevated
    }:
        if _scalar(db.execute("SELECT pg_has_role(%s,%s,'MEMBER')", (app, target))):
            raise ValueError("Runtime role is a member of a privileged role")


def provision(db: psycopg.Connection, migrator: str, app: str) -> None:
    _require_admin(db)
    for role, password_key in (
        (migrator, "TWF_PG_MIGRATOR_PASSWORD"),
        (app, "TWF_PG_APP_PASSWORD"),
    ):
        if not _role_exists(db, role):
            password = os.environ.get(password_key)
            if not password:
                raise ValueError(f"Set {password_key} to create {role}")
            db.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
    _require_roles(db, migrator, app)


def prepare_fresh(db: psycopg.Connection, schema: str, migrator: str, app: str) -> None:
    """Give migrator creation authority before first Alembic run, only on empty schema."""
    _require_admin(db)
    _require_roles(db, migrator, app)
    database = _scalar(db.execute("SELECT current_database()"))
    if database in ("postgres", "template0", "template1"):
        raise ValueError("Refusing to prepare a system database")
    if db.execute(
        "SELECT 1 FROM pg_class WHERE relnamespace=%s::regnamespace", (schema,)
    ).fetchone():
        raise ValueError("Fresh preparation requires an empty schema")
    db.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
            sql.Identifier(database)
        )
    )
    db.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
            sql.Identifier(database), sql.Identifier(app)
        )
    )
    db.execute(
        sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
            sql.Identifier(database), sql.Identifier(migrator)
        )
    )
    # Ownership transfer does not repair ACLs inherited from the former owner.
    db.execute(
        sql.SQL("GRANT ALL ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(migrator)
        )
    )
    db.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(app)
        )
    )
    db.execute(
        sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(schema))
    )
    db.execute(
        sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(
            sql.Identifier(schema), sql.Identifier(app)
        )
    )
    db.execute(
        sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(
            sql.Identifier(schema), sql.Identifier(migrator)
        )
    )
    db.execute(
        sql.SQL("GRANT ALL ON SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.Identifier(migrator)
        )
    )
    db.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.Identifier(app)
        )
    )


def inventory(db: psycopg.Connection, schema: str) -> None:
    print(
        "database",
        db.execute(
            "SELECT current_database(),pg_get_userbyid(datdba),datacl FROM pg_database "
            "WHERE datname=current_database()"
        ).fetchone(),
    )
    print(
        "schema",
        db.execute(
            "SELECT nspname,pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=%s",
            (schema,),
        ).fetchone(),
    )
    print(
        "relations",
        db.execute(
            "SELECT relkind,pg_get_userbyid(relowner),count(*) FROM pg_class "
            "WHERE relnamespace=%s::regnamespace AND relkind IN ('r','p','v','m','S','f') "
            "GROUP BY 1,2 ORDER BY 1,2",
            (schema,),
        ).fetchall(),
    )
    print(
        "functions",
        db.execute(
            "SELECT pg_get_userbyid(proowner),count(*) FROM pg_proc "
            "WHERE pronamespace=%s::regnamespace GROUP BY 1",
            (schema,),
        ).fetchall(),
    )
    print(
        "triggers",
        db.execute(
            "SELECT c.relname,t.tgname,t.tgenabled,pg_get_userbyid(p.proowner) "
            "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_proc p ON p.oid=t.tgfoid "
            "WHERE c.relnamespace=%s::regnamespace AND NOT t.tgisinternal "
            "ORDER BY c.relname,t.tgname",
            (schema,),
        ).fetchall(),
    )
    print(
        "relation_acl",
        db.execute(
            "SELECT relname,relacl FROM pg_class WHERE relnamespace=%s::regnamespace "
            "AND relkind IN ('r','p','v','m','S','f') ORDER BY relname",
            (schema,),
        ).fetchall(),
    )


def harden(db: psycopg.Connection, schema: str, migrator: str, app: str) -> None:
    _require_admin(db)
    _require_roles(db, migrator, app)
    database = _scalar(db.execute("SELECT current_database()"))
    if database in ("postgres", "template0", "template1"):
        raise ValueError("Refusing to alter a system database")
    if not db.execute(
        "SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema,)
    ).fetchone():
        raise ValueError("Application schema does not exist")
    if not db.execute(
        "SELECT 1 FROM pg_class WHERE relnamespace=%s::regnamespace AND relname='twf_queue_events'",
        (schema,),
    ).fetchone():
        raise ValueError("Run Alembic to the OE-3 head before cutover")
    revision = db.execute(
        sql.SQL("SELECT version_num FROM {}.alembic_version").format(
            sql.Identifier(schema)
        )
    ).fetchall()
    if revision != [(EXPECTED_HEAD,)]:
        raise ValueError("Expected exact OE-3 Alembic head before role cutover")
    # One PostgreSQL transaction covers ownership and ACL changes. No row is copied.
    db.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
            sql.Identifier(database)
        )
    )
    db.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
            sql.Identifier(database), sql.Identifier(app)
        )
    )
    db.execute(
        sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
            sql.Identifier(database), sql.Identifier(migrator)
        )
    )
    # Ownership transfer does not repair ACLs inherited from the former owner.
    db.execute(
        sql.SQL("GRANT ALL ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(migrator)
        )
    )
    db.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(app)
        )
    )
    db.execute(
        sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(schema))
    )
    db.execute(
        sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(
            sql.Identifier(schema), sql.Identifier(app)
        )
    )
    db.execute(
        sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(
            sql.Identifier(schema), sql.Identifier(migrator)
        )
    )
    db.execute(
        sql.SQL("GRANT ALL ON SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.Identifier(migrator)
        )
    )
    db.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.Identifier(app)
        )
    )
    relations = db.execute(
        "SELECT relname,relkind FROM pg_class WHERE relnamespace=%s::regnamespace "
        "AND relkind IN ('r','p','v','m','S','f') ORDER BY relkind,relname",
        (schema,),
    ).fetchall()
    kinds = {
        "r": "TABLE",
        "p": "TABLE",
        "v": "VIEW",
        "m": "MATERIALIZED VIEW",
        "S": "SEQUENCE",
        "f": "FOREIGN TABLE",
    }
    for name, kind in relations:
        db.execute(
            sql.SQL("ALTER {} {}.{} OWNER TO {}").format(
                sql.SQL(kinds[kind]),
                sql.Identifier(schema),
                sql.Identifier(name),
                sql.Identifier(migrator),
            )
        )
    functions = db.execute(
        "SELECT p.proname,pg_get_function_identity_arguments(p.oid),p.prokind "
        "FROM pg_proc p WHERE p.pronamespace=%s::regnamespace ORDER BY p.proname",
        (schema,),
    ).fetchall()
    for name, args, kind in functions:
        if kind not in ("f", "p"):
            raise ValueError(
                "Unexpected aggregate/window function; review ownership manually"
            )
        object_type = "PROCEDURE" if kind == "p" else "FUNCTION"
        db.execute(
            sql.SQL("ALTER {} {}.{}({}) OWNER TO {}").format(
                sql.SQL(object_type),
                sql.Identifier(schema),
                sql.Identifier(name),
                sql.SQL(args),
                sql.Identifier(migrator),
            )
        )
    db.execute(
        sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}").format(
            sql.Identifier(schema), sql.Identifier(app)
        )
    )
    db.execute(
        sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA {} FROM {}").format(
            sql.Identifier(schema), sql.Identifier(app)
        )
    )
    for name, kind in relations:
        if kind == "S":
            db.execute(
                sql.SQL("GRANT USAGE, SELECT ON SEQUENCE {}.{} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(name), sql.Identifier(app)
                )
            )
        elif name == "alembic_version":
            db.execute(
                sql.SQL("GRANT SELECT ON TABLE {}.{} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(name), sql.Identifier(app)
                )
            )
        elif name in IMMUTABLE_EVENT_TABLES:
            db.execute(
                sql.SQL("GRANT SELECT, INSERT ON TABLE {}.{} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(name), sql.Identifier(app)
                )
            )
        else:
            privileges = "SELECT, INSERT"
            if name not in APPEND_ONLY_EVIDENCE_TABLES:
                privileges += ", UPDATE"
            if name in REQUIRED_DELETE_TABLES:
                privileges += ", DELETE"
            db.execute(
                sql.SQL("GRANT {} ON TABLE {}.{} TO {}").format(
                    sql.SQL(privileges),
                    sql.Identifier(schema),
                    sql.Identifier(name),
                    sql.Identifier(app),
                )
            )
    # The trigger continues to execute; runtime cannot invoke/replace its function.
    for function in ("twf_queue_event_immutable", "twf_order_event_immutable"):
        if not any(name == function for name, _, _ in functions):
            continue
        db.execute(
            sql.SQL("REVOKE ALL ON FUNCTION {}.{}() FROM PUBLIC").format(
                sql.Identifier(schema), sql.Identifier(function)
            )
        )
        db.execute(
            sql.SQL("REVOKE ALL ON FUNCTION {}.{}() FROM {}").format(
                sql.Identifier(schema), sql.Identifier(function), sql.Identifier(app)
            )
        )
    _require_roles(db, migrator, app)


def verify(db: psycopg.Connection, schema: str, migrator: str, app: str) -> None:
    _require_roles(db, migrator, app)
    database = _scalar(db.execute("SELECT current_database()"))
    tables = [
        name
        for (name,) in db.execute(
            "SELECT relname FROM pg_class WHERE relnamespace=%s::regnamespace "
            "AND relkind IN ('r','p') ORDER BY relname",
            (schema,),
        ).fetchall()
    ]
    delete_grants = {
        name
        for name in tables
        if _scalar(
            db.execute(
                "SELECT has_table_privilege(%s,%s,'DELETE')", (app, f"{schema}.{name}")
            )
        )
    }
    checks = [
        (
            "DELETE grants match explicit allowlist",
            delete_grants == REQUIRED_DELETE_TABLES,
        ),
        (
            "append-only evidence has no UPDATE",
            all(
                not _scalar(
                    db.execute(
                        "SELECT has_table_privilege(%s,%s,'UPDATE')",
                        (app, f"{schema}.{name}"),
                    )
                )
                for name in APPEND_ONLY_EVIDENCE_TABLES
            ),
        ),
        (
            "Order audit grants are SELECT/INSERT only",
            all(
                _scalar(
                    db.execute(
                        "SELECT has_table_privilege(%s,%s,%s)",
                        (app, f"{schema}.twf_order_events", privilege),
                    )
                )
                == (privilege in ("SELECT", "INSERT"))
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
            ),
        ),
        (
            "database owner",
            _scalar(
                db.execute(
                    "SELECT pg_get_userbyid(datdba) FROM pg_database "
                    "WHERE datname=current_database()"
                )
            )
            == migrator,
        ),
        (
            "migrator has database migration rights",
            all(
                _scalar(
                    db.execute(
                        "SELECT has_database_privilege(%s,%s,%s)",
                        (migrator, database, privilege),
                    )
                )
                for privilege in ("CONNECT", "CREATE", "TEMP")
            ),
        ),
        (
            "migrator has schema migration rights",
            all(
                _scalar(
                    db.execute(
                        "SELECT has_schema_privilege(%s,%s,%s)",
                        (migrator, schema, privilege),
                    )
                )
                for privilege in ("USAGE", "CREATE")
            ),
        ),
        (
            "schema owner",
            _scalar(
                db.execute(
                    "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=%s",
                    (schema,),
                )
            )
            == migrator,
        ),
        (
            "relations owned by migrator",
            _scalar(
                db.execute(
                    "SELECT count(*) FROM pg_class WHERE relnamespace=%s::regnamespace "
                    "AND relkind IN ('r','p','v','m','S','f') "
                    "AND pg_get_userbyid(relowner)<>%s",
                    (schema, migrator),
                )
            )
            == 0,
        ),
        (
            "functions owned by migrator",
            _scalar(
                db.execute(
                    "SELECT count(*) FROM pg_proc WHERE pronamespace=%s::regnamespace "
                    "AND pg_get_userbyid(proowner)<>%s",
                    (schema, migrator),
                )
            )
            == 0,
        ),
        (
            "F1 reciprocal constraints present",
            _scalar(
                db.execute(
                    "SELECT count(*) FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid "
                    "WHERE r.relnamespace=%s::regnamespace AND c.contype='f' "
                    "AND c.convalidated AND c.conname IN "
                    "('fk_twf_orders_queue_binding','fk_twf_queue_entries_order_binding')",
                    (schema,),
                )
            )
            == 2,
        ),
        (
            "Order audit trigger enabled",
            db.execute(
                "SELECT t.tgenabled FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid "
                "WHERE r.relnamespace=%s::regnamespace "
                "AND r.relname='twf_order_events' "
                "AND t.tgname='trg_twf_order_events_immutable'",
                (schema,),
            ).fetchone()
            == ("O",),
        ),
        (
            "Order audit function cannot be executed directly",
            not _scalar(
                db.execute(
                    "SELECT has_function_privilege(%s,%s,'EXECUTE')",
                    (app, f"{schema}.twf_order_event_immutable()"),
                )
            ),
        ),
        (
            "F2 audit trigger enabled",
            db.execute(
                "SELECT t.tgenabled FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid "
                "WHERE r.relnamespace=%s::regnamespace "
                "AND r.relname='twf_queue_events' "
                "AND t.tgname='trg_twf_queue_events_immutable'",
                (schema,),
            ).fetchone()
            == ("O",),
        ),
        (
            "F2 function is invoker-security",
            db.execute(
                "SELECT NOT p.prosecdef FROM pg_proc p "
                "WHERE p.pronamespace=%s::regnamespace "
                "AND p.proname='twf_queue_event_immutable'",
                (schema,),
            ).fetchone()
            == (True,),
        ),
        (
            "runtime cannot execute audit function directly",
            not _scalar(
                db.execute(
                    "SELECT has_function_privilege(%s,%s,'EXECUTE')",
                    (app, f"{schema}.twf_queue_event_immutable()"),
                )
            ),
        ),
        (
            "runtime cannot CREATE in schema",
            not _scalar(
                db.execute("SELECT has_schema_privilege(%s,%s,'CREATE')", (app, schema))
            ),
        ),
        (
            "runtime cannot CREATE in database",
            not _scalar(
                db.execute(
                    "SELECT has_database_privilege(%s,%s,'CREATE')", (app, database)
                )
            ),
        ),
        (
            "runtime cannot create temporary shadow objects",
            not _scalar(
                db.execute(
                    "SELECT has_database_privilege(%s,%s,'TEMP')", (app, database)
                )
            ),
        ),
        (
            "runtime owns no non-system schema",
            _scalar(
                db.execute(
                    "SELECT count(*) FROM pg_namespace WHERE pg_get_userbyid(nspowner)=%s "
                    "AND left(nspname,3)<>'pg_' AND nspname<>'information_schema'",
                    (app,),
                )
            )
            == 0,
        ),
        (
            "runtime cannot mutate Queue audit",
            not _scalar(
                db.execute(
                    "SELECT has_table_privilege(%s,%s,'UPDATE,DELETE')",
                    (app, f"{schema}.twf_queue_events"),
                )
            ),
        ),
        (
            "runtime cannot edit Alembic head",
            not _scalar(
                db.execute(
                    "SELECT has_table_privilege(%s,%s,'INSERT,UPDATE,DELETE')",
                    (app, f"{schema}.alembic_version"),
                )
            ),
        ),
    ]
    for label, passed in checks:
        print(("PASS" if passed else "FAIL"), label)
    if not all(passed for _, passed in checks):
        raise ValueError("PostgreSQL privilege verification failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("inventory", "provision", "prepare-fresh", "harden", "verify"),
    )
    args = parser.parse_args()
    migrator = _ident_env("TWF_PG_MIGRATOR_ROLE", "twf_migrator")
    app = _ident_env("TWF_PG_APP_ROLE", "twf_app")
    schema = _ident_env("TWF_PG_SCHEMA", "public")
    try:
        with _connection() as db:
            if args.action == "inventory":
                inventory(db, schema)
            elif args.action == "provision":
                provision(db, migrator, app)
            elif args.action == "prepare-fresh":
                prepare_fresh(db, schema, migrator, app)
            elif args.action == "harden":
                harden(db, schema, migrator, app)
                verify(db, schema, migrator, app)
            else:
                verify(db, schema, migrator, app)
    except (ValueError, psycopg.Error) as exc:
        # Never print a DSN, password, or raw server exception.
        print(
            f"PostgreSQL role operation refused: {type(exc).__name__}", file=sys.stderr
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
