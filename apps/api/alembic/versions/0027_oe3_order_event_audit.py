"""Make durable TWF Order events append-only at the database boundary."""

from alembic import op

revision = "0027_oe3_order_event_audit"
down_revision = "0026_oe3_queue_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE FUNCTION twf_order_event_immutable() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
            "'TWF Order events are immutable' USING ERRCODE = '23514'; END $$"
        )
        op.execute(
            "CREATE TRIGGER trg_twf_order_events_immutable BEFORE UPDATE OR DELETE "
            "ON twf_order_events FOR EACH ROW EXECUTE FUNCTION twf_order_event_immutable()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            connection.exec_driver_sql(
                f"CREATE TRIGGER trg_twf_order_events_no_{action.lower()} "
                f"BEFORE {action} ON twf_order_events BEGIN "
                "SELECT RAISE(ABORT, 'TWF Order events are immutable'); END"
            )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_twf_order_events_immutable ON twf_order_events")
        op.execute("DROP FUNCTION twf_order_event_immutable()")
    else:
        for action in ("update", "delete"):
            connection.exec_driver_sql(f"DROP TRIGGER trg_twf_order_events_no_{action}")
