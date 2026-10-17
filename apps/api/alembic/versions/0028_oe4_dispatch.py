"""Admission-time dispatch mode and durable Queue/Broker bridge."""

from datetime import UTC, datetime
from sqlite3 import Connection
from typing import cast
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import context, op

revision = "0028_oe4_dispatch"
down_revision = "0027_oe3_order_event_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    c = op.get_bind()
    op.add_column("manual_order_previews", sa.Column("source_ref", sa.String(256)))
    # New tables only; the accepted Order lifecycle remains unchanged.
    op.create_table(
        "twf_public_id_counters",
        sa.Column("bucket", sa.String(40), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False),
    )
    op.create_table(
        "twf_order_public_ids",
        sa.Column(
            "twf_order_id", sa.Uuid(), sa.ForeignKey("twf_orders.twf_order_id"), primary_key=True
        ),
        sa.Column("public_order_id", sa.String(64), nullable=False, unique=True),
    )
    op.create_table(
        "twf_queue_dispatch_policies",
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column(
            "broker_account_id", sa.Uuid(), sa.ForeignKey("broker_accounts.id"), primary_key=True
        ),
        sa.Column("current_dispatch_mode", sa.String(8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "current_dispatch_mode IN ('MANUAL','AUTO')", name="ck_twf_queue_dispatch_policies_mode"
        ),
    )
    op.create_table(
        "twf_queue_policy_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "broker_account_id", sa.Uuid(), sa.ForeignKey("broker_accounts.id"), nullable=False
        ),
        sa.Column("previous_mode", sa.String(8), nullable=False),
        sa.Column("new_mode", sa.String(8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_id", "broker_account_id", "version", name="uq_twf_policy_version"
        ),
    )
    if c.dialect.name == "sqlite":
        # Same migration-only trusted connection technique as 0026.
        raw = cast(Connection, c.connection.driver_connection)
        raw.autocommit = True
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.autocommit = False
    with op.batch_alter_table("twf_queue_entries") as b:
        b.drop_constraint(
            op.f(
                "ck_twf_queue_entries_ck_twf_queue_entries_active_state"
                if c.dialect.name == "postgresql"
                else "ck_twf_queue_entries_active_state"
            ),
            type_="check",
        )
        b.create_check_constraint(
            "active_state",
            "queue_state IN "
            "('READY','HELD','DISPATCHING','DISPATCHED','FAILED','RECONCILIATION_REQUIRED','CANCELLED')",
        )
        b.add_column(
            sa.Column(
                "effective_dispatch_mode", sa.String(8), nullable=False, server_default="MANUAL"
            )
        )
        b.add_column(sa.Column("broker_account_id", sa.Uuid(), nullable=True))
        b.create_foreign_key(
            "fk_twf_queue_dispatch_account", "broker_accounts", ["broker_account_id"], ["id"]
        )
        b.add_column(sa.Column("policy_version", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(
            sa.Column("source_kind", sa.String(32), nullable=False, server_default="MANUAL")
        )
        b.add_column(sa.Column("source_reference", sa.String(256)))
        b.add_column(sa.Column("public_queue_id", sa.String(64)))
        b.create_unique_constraint("uq_twf_queue_public_id", ["public_queue_id"])
        b.create_check_constraint("dispatch_mode", "effective_dispatch_mode IN ('MANUAL','AUTO')")
    op.add_column(
        "twf_queue_events", sa.Column("details", sa.JSON(), nullable=False, server_default="{}")
    )
    op.create_table(
        "twf_dispatch_attempts",
        sa.Column("dispatch_attempt_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "queue_entry_id",
            sa.Uuid(),
            sa.ForeignKey("twf_queue_entries.queue_entry_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "broker_intent_id",
            sa.Uuid(),
            sa.ForeignKey("broker_order_intents.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("authority", sa.String(8), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(32)),
    )
    if context.is_offline_mode():
        # PostgreSQL offline plans must retain the same deterministic backfill.
        for table, idcol, datecol, kind, fmt in (
            ("twf_orders", "twf_order_id", "created_at", "ORD", "YYYYMMDDHH24MISS"),
            ("twf_queue_entries", "queue_entry_id", "admitted_at", "QID", "YYYYMMDD-HH24MI"),
        ):
            ranked = (
                f"WITH buckets AS (SELECT {idcol} AS id, {datecol} AS at, "
                f"'{kind}-' || to_char({datecol} AT TIME ZONE 'Asia/Kolkata', '{fmt}') AS bucket "
                f"FROM {table}), ranked AS (SELECT id, bucket, "
                "row_number() OVER (PARTITION BY bucket ORDER BY at, id) AS n FROM buckets) "
            )
            alias = "bucket || '-' || lpad(n::text, greatest(3,length(n::text)), '0')"
            if kind == "ORD":
                op.execute(
                    ranked
                    + "INSERT INTO twf_order_public_ids (twf_order_id,public_order_id) "
                    + f"SELECT id, {alias} FROM ranked"
                )
            else:
                op.execute(
                    ranked + f"UPDATE twf_queue_entries q SET public_queue_id={alias} "
                    "FROM ranked WHERE q.queue_entry_id=ranked.id"
                )
            op.execute(
                ranked + "INSERT INTO twf_public_id_counters (bucket,value) "
                "SELECT bucket,max(n) FROM ranked GROUP BY bucket"
            )
    else:
        counters: dict[str, int] = {}
        for table, idcol, datecol, kind in [
            ("twf_orders", "twf_order_id", "created_at", "ORD"),
            ("twf_queue_entries", "queue_entry_id", "admitted_at", "QID"),
        ]:
            for row in c.execute(
                sa.text(f"SELECT {idcol}, {datecol} FROM {table} ORDER BY {datecol}, {idcol}")
            ).all():
                at = row[1] if isinstance(row[1], datetime) else datetime.fromisoformat(row[1])
                at = at.replace(tzinfo=UTC) if at.tzinfo is None else at
                bucket = (
                    kind
                    + "-"
                    + at.astimezone(ZoneInfo("Asia/Kolkata")).strftime(
                        "%Y%m%d%H%M%S" if kind == "ORD" else "%Y%m%d-%H%M"
                    )
                )
                counters[bucket] = counters.get(bucket, 0) + 1
                alias = f"{bucket}-{counters[bucket]:03d}"
                if kind == "ORD":
                    c.execute(
                        sa.text(
                            "INSERT INTO twf_order_public_ids "
                            "(twf_order_id,public_order_id) VALUES (:id,:alias)"
                        ),
                        {"id": row[0], "alias": alias},
                    )
                else:
                    c.execute(
                        sa.text(
                            "UPDATE twf_queue_entries SET public_queue_id=:alias WHERE "
                            "queue_entry_id=:id"
                        ),
                        {"id": row[0], "alias": alias},
                    )
        for bucket, value in counters.items():
            c.execute(
                sa.text(
                    "INSERT INTO twf_public_id_counters (bucket,value) VALUES (:bucket,:value)"
                ),
                {"bucket": bucket, "value": value},
            )
    if c.dialect.name == "postgresql":
        op.execute(
            "UPDATE twf_queue_entries q SET "
            "source_kind=o.payload->'provenance'->>'source', "
            "source_reference=o.payload->'provenance'->>'source_ref' FROM twf_orders o "
            "WHERE q.twf_order_id=o.twf_order_id"
        )
    else:
        op.execute(
            "UPDATE twf_queue_entries SET source_kind=(SELECT "
            "json_extract(payload,'$.provenance.source') FROM twf_orders WHERE "
            "twf_order_id=twf_queue_entries.twf_order_id), source_reference=(SELECT "
            "json_extract(payload,'$.provenance.source_ref') FROM twf_orders WHERE "
            "twf_order_id=twf_queue_entries.twf_order_id)"
        )
    fields = (
        "effective_dispatch_mode",
        "broker_account_id",
        "policy_version",
        "source_kind",
        "source_reference",
        "public_queue_id",
    )
    if c.dialect.name == "postgresql":
        changed = " OR ".join(f"NEW.{f} IS DISTINCT FROM OLD.{f}" for f in fields)
        op.execute(
            f"CREATE FUNCTION twf_queue_snapshot_immutable() RETURNS trigger LANGUAGE "
            f"plpgsql AS $$ BEGIN IF {changed} THEN RAISE EXCEPTION 'Queue admission "
            f"snapshot is immutable' USING ERRCODE='23514'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER trg_twf_queue_snapshot BEFORE UPDATE ON twf_queue_entries "
            "FOR EACH ROW EXECUTE FUNCTION twf_queue_snapshot_immutable()"
        )
        op.execute(
            "CREATE TRIGGER trg_twf_queue_policy_events_immutable BEFORE UPDATE OR "
            "DELETE ON twf_queue_policy_events FOR EACH ROW EXECUTE FUNCTION "
            "twf_queue_event_immutable()"
        )
    else:
        changed = " OR ".join(f"NEW.{f} IS NOT OLD.{f}" for f in fields)
        op.execute(
            f"CREATE TRIGGER trg_twf_queue_snapshot BEFORE UPDATE ON twf_queue_entries "
            f"WHEN {changed} BEGIN SELECT RAISE(ABORT,'Queue admission snapshot is "
            f"immutable'); END"
        )
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER trg_twf_queue_policy_events_no_{action.lower()} BEFORE "
                f"{action} ON twf_queue_policy_events BEGIN SELECT RAISE(ABORT,'Queue "
                f"policy history is immutable'); END"
            )
        if c.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("OE-4 migration foreign-key validation failed")

    # Durable aliases and claim identity cannot be rewritten by runtime DML.
    immutable_attempt_fields = (
        "dispatch_attempt_id",
        "queue_entry_id",
        "owner_id",
        "broker_intent_id",
        "authority",
        "actor",
        "claimed_at",
    )
    if c.dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER trg_twf_order_public_ids_immutable BEFORE UPDATE OR DELETE "
            "ON twf_order_public_ids FOR EACH ROW EXECUTE FUNCTION "
            "twf_queue_event_immutable()"
        )
        changed = " OR ".join(f"NEW.{f} IS DISTINCT FROM OLD.{f}" for f in immutable_attempt_fields)
        op.execute(
            f"CREATE FUNCTION twf_dispatch_attempt_identity_immutable() RETURNS trigger "
            f"LANGUAGE plpgsql AS $$ BEGIN IF {changed} THEN RAISE EXCEPTION 'Dispatch "
            f"claim identity is immutable' USING ERRCODE='23514'; END IF; RETURN NEW; "
            f"END $$"
        )
        op.execute(
            "CREATE TRIGGER trg_twf_dispatch_identity BEFORE UPDATE ON "
            "twf_dispatch_attempts FOR EACH ROW EXECUTE FUNCTION "
            "twf_dispatch_attempt_identity_immutable()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER trg_twf_order_public_ids_no_{action.lower()} BEFORE "
                f"{action} ON twf_order_public_ids BEGIN SELECT RAISE(ABORT,'Order "
                f"alias is immutable'); END"
            )
        changed = " OR ".join(f"NEW.{f} IS NOT OLD.{f}" for f in immutable_attempt_fields)
        op.execute(
            f"CREATE TRIGGER trg_twf_dispatch_identity BEFORE UPDATE ON "
            f"twf_dispatch_attempts WHEN {changed} BEGIN SELECT RAISE(ABORT,'Dispatch "
            f"claim identity is immutable'); END"
        )


def downgrade() -> None:
    c = op.get_bind()
    if (
        c.scalar(sa.text("SELECT count(*) FROM twf_dispatch_attempts"))
        or c.scalar(sa.text("SELECT count(*) FROM twf_queue_policy_events"))
        or c.scalar(
            sa.text(
                "SELECT count(*) FROM twf_queue_entries WHERE queue_state NOT IN "
                "('READY','HELD') OR effective_dispatch_mode <> 'MANUAL'"
            )
        )
        or c.scalar(sa.text("SELECT count(*) FROM manual_order_previews WHERE source <> 'MANUAL'"))
    ):
        raise RuntimeError(
            "OE-4 downgrade refused: execution or source audit requires a verified backup"
        )
    if c.dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_twf_queue_snapshot ON twf_queue_entries")
        op.execute("DROP FUNCTION twf_queue_snapshot_immutable()")
        op.execute("DROP TRIGGER trg_twf_queue_policy_events_immutable ON twf_queue_policy_events")
    else:
        raw = cast(Connection, c.connection.driver_connection)
        raw.autocommit = True
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.autocommit = False
        op.execute("DROP TRIGGER trg_twf_queue_snapshot")
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER trg_twf_queue_policy_events_no_{action}")
    op.drop_table("twf_dispatch_attempts")
    if c.dialect.name == "postgresql":
        op.execute("DROP FUNCTION twf_dispatch_attempt_identity_immutable()")
    op.drop_table("twf_queue_policy_events")
    op.drop_table("twf_queue_dispatch_policies")
    op.drop_table("twf_order_public_ids")
    op.drop_table("twf_public_id_counters")
    with op.batch_alter_table("twf_queue_entries") as b:
        b.drop_constraint(op.f("ck_twf_queue_entries_active_state"), type_="check")
        b.drop_constraint(op.f("ck_twf_queue_entries_dispatch_mode"), type_="check")
        b.drop_constraint("fk_twf_queue_dispatch_account", type_="foreignkey")
        b.drop_constraint("uq_twf_queue_public_id", type_="unique")
        for column in (
            "effective_dispatch_mode",
            "broker_account_id",
            "policy_version",
            "source_kind",
            "source_reference",
            "public_queue_id",
        ):
            b.drop_column(column)
        b.create_check_constraint(
            op.f(
                "ck_twf_queue_entries_ck_twf_queue_entries_active_state"
                if c.dialect.name == "postgresql"
                else "ck_twf_queue_entries_active_state"
            ),
            "queue_state IN ('READY','HELD')",
        )
    # Native DROP COLUMN preserves the pre-existing append-only triggers.
    op.drop_column("twf_queue_events", "details")
    op.drop_column("manual_order_previews", "source_ref")
    if c.dialect.name == "sqlite" and c.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("OE-4 downgrade foreign-key validation failed")
