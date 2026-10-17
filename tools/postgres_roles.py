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
APPEND_ONLY_TABLES = frozenset(
    {
        "preference_changes",
        "scanner_v2_runs",
        "twf_order_events",
        "twf_order_public_ids",
        "twf_queue_events",
        "twf_queue_policy_events",
    }
)
MUTABLE_RUNTIME_TABLES = frozenset(
    {
        "auth_sessions",
        "broker_accounts",
        "broker_attempts",
        "broker_order_intents",
        "broker_secrets",
        "dhan_market_data_connections",
        "dhan_market_data_secrets",
        "discovery_active_slots",
        "discovery_comparison_scopes",
        "discovery_episodes",
        "discovery_llm_explanations",
        "discovery_market_context",
        "discovery_observations",
        "discovery_projection_checkpoints",
        "discovery_scan_admissions",
        "discovery_scan_evidence_series",
        "discovery_scan_matches",
        "discovery_scan_runs",
        "discovery_settings",
        "discovery_snapshots",
        "discovery_temporal_lanes",
        "discovery_transitions",
        "fno_liquidity_cache",
        "instrument_metadata",
        "instrument_metadata_refreshes",
        "manual_order_previews",
        "mcp_connections",
        "mcp_oauth_attempts",
        "mcp_operations",
        "mcp_secrets",
        "preference_profiles",
        "scanner_v2_derivative_templates",
        "scanner_v2_saved",
        "twf_dispatch_attempts",
        "twf_orders",
        "twf_public_id_counters",
        "twf_queue_dispatch_policies",
        "twf_queue_entries",
        "user_preferences",
        "users",
        "watchlist_activity",
        "watchlist_items",
        "watchlist_notes",
        "watchlists",
    }
)
READ_ONLY_TABLES = frozenset({"alembic_version"})
REGISTERED_RUNTIME_TABLES = (
    READ_ONLY_TABLES | APPEND_ONLY_TABLES | MUTABLE_RUNTIME_TABLES
)
RUNTIME_SEQUENCES: frozenset[str] = frozenset()
PROTECTED_TRIGGER_FUNCTIONS = frozenset(
    {
        "twf_dispatch_attempt_identity_immutable",
        "twf_order_event_immutable",
        "twf_queue_event_immutable",
        "twf_queue_snapshot_immutable",
    }
)
EXPECTED_HEAD = "0028_oe4_dispatch"


def _expected_table_privileges(name: str) -> frozenset[str]:
    if name in READ_ONLY_TABLES:
        return frozenset({"SELECT"})
    if name in APPEND_ONLY_TABLES:
        return frozenset({"SELECT", "INSERT"})
    if name in MUTABLE_RUNTIME_TABLES:
        privileges = {"SELECT", "INSERT", "UPDATE"}
        if name in REQUIRED_DELETE_TABLES:
            privileges.add("DELETE")
        return frozenset(privileges)
    raise ValueError("Unregistered runtime table")


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
        sql.SQL("GRANT CONNECT, CREATE, TEMPORARY ON DATABASE {} TO {}").format(
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
        sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {}").format(
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
        raise ValueError("Run Alembic to the OE-4 head before role hardening")
    revision = db.execute(
        sql.SQL("SELECT version_num FROM {}.alembic_version").format(
            sql.Identifier(schema)
        )
    ).fetchall()
    if revision != [(EXPECTED_HEAD,)]:
        raise ValueError("Expected exact OE-4 Alembic head before role hardening")
    discovered = db.execute(
        "SELECT relname,relkind FROM pg_class WHERE relnamespace=%s::regnamespace "
        "AND relkind IN ('r','p','v','m','S','f') ORDER BY relkind,relname",
        (schema,),
    ).fetchall()
    discovered_tables = {name for name, kind in discovered if kind in ("r", "p")}
    discovered_sequences = {name for name, kind in discovered if kind == "S"}
    discovered_other = {
        (name, kind) for name, kind in discovered if kind not in ("r", "p", "S")
    }
    if discovered_tables != REGISTERED_RUNTIME_TABLES:
        raise ValueError(
            "Runtime table privilege registry does not match the migrated schema"
        )
    if discovered_sequences != RUNTIME_SEQUENCES:
        raise ValueError(
            "Runtime sequence privilege registry does not match the migrated schema"
        )
    if discovered_other:
        raise ValueError(
            "Runtime relation privilege registry does not cover a schema object"
        )
    discovered_functions = {
        name
        for (name,) in db.execute(
            "SELECT p.proname FROM pg_proc p WHERE p.pronamespace=%s::regnamespace",
            (schema,),
        ).fetchall()
    }
    if discovered_functions != PROTECTED_TRIGGER_FUNCTIONS:
        raise ValueError(
            "Runtime function privilege registry does not match the migrated schema"
        )
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
        sql.SQL("GRANT CONNECT, CREATE, TEMPORARY ON DATABASE {} TO {}").format(
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
        sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.Identifier(migrator)
        )
    )
    db.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.Identifier(app)
        )
    )
    relations = discovered
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
        elif name in READ_ONLY_TABLES:
            db.execute(
                sql.SQL("GRANT SELECT ON TABLE {}.{} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(name), sql.Identifier(app)
                )
            )
        elif name in APPEND_ONLY_TABLES:
            db.execute(
                sql.SQL("GRANT SELECT, INSERT ON TABLE {}.{} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(name), sql.Identifier(app)
                )
            )
        elif name in MUTABLE_RUNTIME_TABLES:
            privileges = "SELECT, INSERT, UPDATE"
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
    for function in sorted(PROTECTED_TRIGGER_FUNCTIONS):
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
    sequence_names = {
        name
        for (name,) in db.execute(
            "SELECT relname FROM pg_class WHERE relnamespace=%s::regnamespace "
            "AND relkind='S' ORDER BY relname",
            (schema,),
        ).fetchall()
    }
    function_names = {
        name
        for (name,) in db.execute(
            "SELECT proname FROM pg_proc WHERE pronamespace=%s::regnamespace ORDER BY proname",
            (schema,),
        ).fetchall()
    }
    exact_table_grants = set(tables) == REGISTERED_RUNTIME_TABLES and all(
        bool(
            _scalar(
                db.execute(
                    "SELECT has_table_privilege(%s,%s,%s)",
                    (app, f"{schema}.{name}", privilege),
                )
            )
        )
        == (privilege in _expected_table_privileges(name))
        for name in tables
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
    )
    checks = [
        ("table registry matches schema", set(tables) == REGISTERED_RUNTIME_TABLES),
        ("table grants match explicit registry", exact_table_grants),
        ("sequence registry matches schema", sequence_names == RUNTIME_SEQUENCES),
        (
            "function registry matches schema",
            function_names == PROTECTED_TRIGGER_FUNCTIONS,
        ),
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
                for name in APPEND_ONLY_TABLES
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
            "runtime cannot execute protected functions directly",
            all(
                not _scalar(
                    db.execute(
                        "SELECT has_function_privilege(%s,%s,'EXECUTE')",
                        (app, f"{schema}.{function}()"),
                    )
                )
                for function in PROTECTED_TRIGGER_FUNCTIONS
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
