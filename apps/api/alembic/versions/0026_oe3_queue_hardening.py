"""OE-3 commit-time Order/Queue binding and immutable Queue audit."""

import sqlite3

import sqlalchemy as sa
from alembic import op

revision = "0026_oe3_queue_hardening"
down_revision = "0025_twf_queue"
branch_labels = None
depends_on = None


def _validate_existing(connection: sa.Connection) -> None:
    # Refuse ambiguity before touching schema. Existing OE-3 has only QUEUED
    # admitted Orders; later states may carry the binding after this revision.
    bad_entry = connection.execute(
        sa.text(
            "SELECT q.queue_entry_id FROM twf_queue_entries q "
            "LEFT JOIN twf_orders o ON o.twf_order_id=q.twf_order_id "
            "AND o.owner_id=q.owner_id WHERE o.twf_order_id IS NULL "
            "OR o.state <> 'QUEUED' LIMIT 1"
        )
    ).first()
    bad_order = connection.execute(
        sa.text(
            "SELECT o.twf_order_id FROM twf_orders o "
            "LEFT JOIN twf_queue_entries q ON q.twf_order_id=o.twf_order_id "
            "AND q.owner_id=o.owner_id WHERE "
            "(o.state='QUEUED' AND q.queue_entry_id IS NULL) OR "
            "(o.state IN ('DRAFT','READY') AND q.queue_entry_id IS NOT NULL) "
            "LIMIT 1"
        )
    ).first()
    if bad_entry or bad_order:
        raise RuntimeError("OE-3 binding migration refused incoherent 0025 Order/Queue data")


def _sqlite_foreign_keys_off(connection: sa.Connection) -> None:
    # SQLite cannot add a composite FK to an existing table. The copy/swap is
    # transactional; keep FK enforcement off only on this migration connection.
    raw = connection.connection.driver_connection
    assert isinstance(raw, sqlite3.Connection)
    raw.autocommit = True
    raw.execute("PRAGMA foreign_keys=OFF").close()
    raw.autocommit = False
    if raw.execute("PRAGMA foreign_keys").fetchone() != (0,):
        raise RuntimeError("SQLite migration could not disable FKs for table copy")


def _sqlite_check(connection: sa.Connection) -> None:
    faults = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if faults:
        raise RuntimeError("OE-3 binding migration foreign-key validation failed")


def _sqlite_orders_table(name: str, *, bound: bool) -> str:
    binding = (
        """
        queue_entry_id CHAR(32),
        CONSTRAINT uq_twf_orders_queue_binding UNIQUE
            (twf_order_id, owner_id, queue_entry_id),
        CONSTRAINT ck_twf_orders_queue_binding CHECK (
            (state NOT IN ('DRAFT', 'READY') OR queue_entry_id IS NULL) AND
            (state NOT IN ('QUEUED', 'SUBMITTING', 'BROKER_ACCEPTED',
                           'PARTIALLY_FILLED', 'FILLED') OR queue_entry_id IS NOT NULL)
        ),
        CONSTRAINT fk_twf_orders_queue_binding FOREIGN KEY
            (queue_entry_id, twf_order_id, owner_id)
            REFERENCES twf_queue_entries (queue_entry_id, twf_order_id, owner_id)
            ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    """
        if bound
        else ""
    )
    return f"""CREATE TABLE {name} (
        twf_order_id CHAR(32) NOT NULL PRIMARY KEY,
        owner_id CHAR(32) NOT NULL REFERENCES users (id),
        state VARCHAR(32) NOT NULL,
        version INTEGER NOT NULL,
        payload JSON NOT NULL,
        created_by VARCHAR(128) NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        state_reason_code VARCHAR(64),
        state_reason VARCHAR(512),
        {binding}
        CONSTRAINT ck_twf_orders_version_positive CHECK (version > 0),
        CONSTRAINT uq_twf_orders_id_owner UNIQUE (twf_order_id, owner_id)
    )"""


def _sqlite_queue_table(name: str, *, bound: bool) -> str:
    binding = (
        """
        CONSTRAINT fk_twf_queue_entries_order_binding FOREIGN KEY
            (twf_order_id, owner_id, queue_entry_id)
            REFERENCES twf_orders (twf_order_id, owner_id, queue_entry_id)
            ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    """
        if bound
        else ""
    )
    return f"""CREATE TABLE {name} (
        queue_entry_id CHAR(32) NOT NULL PRIMARY KEY,
        twf_order_id CHAR(32) NOT NULL,
        owner_id CHAR(32) NOT NULL,
        queue_state VARCHAR(32) NOT NULL,
        version INTEGER NOT NULL,
        admitted_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        created_by VARCHAR(128) NOT NULL,
        reason_code VARCHAR(64),
        reason_message VARCHAR(512),
        CONSTRAINT fk_twf_queue_entries_order_owner FOREIGN KEY (twf_order_id, owner_id)
            REFERENCES twf_orders (twf_order_id, owner_id) ON DELETE RESTRICT,
        {binding}
        CONSTRAINT uq_twf_queue_entries_order UNIQUE (twf_order_id),
        CONSTRAINT uq_twf_queue_entries_identity UNIQUE
            (queue_entry_id, twf_order_id, owner_id),
        CONSTRAINT ck_twf_queue_entries_version_positive CHECK (version > 0),
        CONSTRAINT ck_twf_queue_entries_active_state CHECK
            (queue_state IN ('READY', 'HELD'))
    )"""


_ORDER_COLUMNS = (
    "twf_order_id,owner_id,state,version,payload,created_by,created_at,"
    "updated_at,state_reason_code,state_reason"
)
_QUEUE_COLUMNS = (
    "queue_entry_id,twf_order_id,owner_id,queue_state,version,"
    "admitted_at,updated_at,created_by,reason_code,reason_message"
)


def _sqlite_swap(connection: sa.Connection, *, bound: bool) -> None:
    connection.exec_driver_sql(_sqlite_orders_table("twf_orders_0026_copy", bound=bound))
    if bound:
        connection.exec_driver_sql(
            f"INSERT INTO twf_orders_0026_copy ({_ORDER_COLUMNS},queue_entry_id) "
            f"SELECT {_ORDER_COLUMNS},(SELECT q.queue_entry_id FROM twf_queue_entries q "
            "WHERE q.twf_order_id=twf_orders.twf_order_id AND q.owner_id=twf_orders.owner_id) "
            "FROM twf_orders"
        )
    else:
        connection.exec_driver_sql(
            f"INSERT INTO twf_orders_0026_copy ({_ORDER_COLUMNS}) "
            f"SELECT {_ORDER_COLUMNS} FROM twf_orders"
        )
    connection.exec_driver_sql(_sqlite_queue_table("twf_queue_entries_0026_copy", bound=bound))
    connection.exec_driver_sql(
        f"INSERT INTO twf_queue_entries_0026_copy ({_QUEUE_COLUMNS}) "
        f"SELECT {_QUEUE_COLUMNS} FROM twf_queue_entries"
    )
    connection.exec_driver_sql("DROP TABLE twf_queue_entries")
    connection.exec_driver_sql("DROP TABLE twf_orders")
    connection.exec_driver_sql("ALTER TABLE twf_orders_0026_copy RENAME TO twf_orders")
    connection.exec_driver_sql(
        "ALTER TABLE twf_queue_entries_0026_copy RENAME TO twf_queue_entries"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_twf_orders_owner_created ON twf_orders (owner_id, created_at)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_twf_queue_entries_owner_fifo ON "
        "twf_queue_entries (owner_id, admitted_at, queue_entry_id)"
    )
    _sqlite_check(connection)


def _event_guards(connection: sa.Connection) -> None:
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE FUNCTION twf_queue_event_immutable() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
            "'TWF Queue events are immutable' USING ERRCODE = '23514'; END $$"
        )
        op.execute(
            "CREATE TRIGGER trg_twf_queue_events_immutable BEFORE UPDATE OR DELETE "
            "ON twf_queue_events FOR EACH ROW EXECUTE FUNCTION twf_queue_event_immutable()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            connection.exec_driver_sql(
                f"CREATE TRIGGER trg_twf_queue_events_no_{action.lower()} "
                f"BEFORE {action} ON twf_queue_events BEGIN "
                "SELECT RAISE(ABORT, 'TWF Queue events are immutable'); END"
            )


def _drop_event_guards(connection: sa.Connection) -> None:
    if connection.dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_twf_queue_events_immutable ON twf_queue_events")
        op.execute("DROP FUNCTION twf_queue_event_immutable()")
    else:
        for action in ("update", "delete"):
            connection.exec_driver_sql(f"DROP TRIGGER trg_twf_queue_events_no_{action}")


def upgrade() -> None:
    connection = op.get_bind()
    if not op.get_context().as_sql:
        _validate_existing(connection)
    if connection.dialect.name == "sqlite":
        _sqlite_foreign_keys_off(connection)
        _sqlite_swap(connection, bound=True)
    else:
        op.add_column("twf_orders", sa.Column("queue_entry_id", sa.Uuid(), nullable=True))
        op.execute(
            "UPDATE twf_orders o SET queue_entry_id=q.queue_entry_id "
            "FROM twf_queue_entries q WHERE q.twf_order_id=o.twf_order_id "
            "AND q.owner_id=o.owner_id"
        )
        op.create_unique_constraint(
            "uq_twf_orders_queue_binding",
            "twf_orders",
            ["twf_order_id", "owner_id", "queue_entry_id"],
        )
        op.create_check_constraint(
            "ck_twf_orders_pre_queue_unbound",
            "twf_orders",
            "state NOT IN ('DRAFT', 'READY') OR queue_entry_id IS NULL",
        )
        op.create_check_constraint(
            "ck_twf_orders_admitted_state_bound",
            "twf_orders",
            "state NOT IN ('QUEUED', 'SUBMITTING', 'BROKER_ACCEPTED', "
            "'PARTIALLY_FILLED', 'FILLED') OR queue_entry_id IS NOT NULL",
        )
        op.create_foreign_key(
            "fk_twf_orders_queue_binding",
            "twf_orders",
            "twf_queue_entries",
            ["queue_entry_id", "twf_order_id", "owner_id"],
            ["queue_entry_id", "twf_order_id", "owner_id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        )
        op.create_foreign_key(
            "fk_twf_queue_entries_order_binding",
            "twf_queue_entries",
            "twf_orders",
            ["twf_order_id", "owner_id", "queue_entry_id"],
            ["twf_order_id", "owner_id", "queue_entry_id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        )
    _event_guards(connection)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        _sqlite_foreign_keys_off(connection)
        _drop_event_guards(connection)
        _sqlite_swap(connection, bound=False)
    else:
        _drop_event_guards(connection)
        op.drop_constraint(
            "fk_twf_queue_entries_order_binding", "twf_queue_entries", type_="foreignkey"
        )
        op.drop_constraint("fk_twf_orders_queue_binding", "twf_orders", type_="foreignkey")
        op.drop_constraint("ck_twf_orders_admitted_state_bound", "twf_orders", type_="check")
        op.drop_constraint("ck_twf_orders_pre_queue_unbound", "twf_orders", type_="check")
        op.drop_constraint("uq_twf_orders_queue_binding", "twf_orders", type_="unique")
        op.drop_column("twf_orders", "queue_entry_id")
