"""Transactional operator aliases; canonical UUIDs remain authoritative."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import event, insert
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper

from twf.infrastructure.dispatch import OrderPublicID, PublicIDCounter
from twf.infrastructure.twf_order import TWFOrderRecord


def allocate(connection: Connection, kind: str, at: datetime) -> str:
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    local = at.astimezone(ZoneInfo("Asia/Kolkata"))
    bucket = kind + "-" + local.strftime("%Y%m%d%H%M%S" if kind == "ORD" else "%Y%m%d-%H%M")
    if connection.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    statement = (
        pg_insert(PublicIDCounter)
        if connection.dialect.name == "postgresql"
        else sqlite_insert(PublicIDCounter)
    ).values(bucket=bucket, value=1)
    number = connection.execute(
        statement.on_conflict_do_update(
            index_elements=[PublicIDCounter.bucket], set_={"value": PublicIDCounter.value + 1}
        ).returning(PublicIDCounter.value)
    ).scalar_one()
    return f"{bucket}-{number:03d}"


@event.listens_for(TWFOrderRecord, "after_insert")
def assign_order_alias(
    mapper: Mapper[TWFOrderRecord], connection: Connection, target: TWFOrderRecord
) -> None:
    connection.execute(
        insert(OrderPublicID).values(
            twf_order_id=target.twf_order_id,
            public_order_id=allocate(connection, "ORD", target.created_at),
        )
    )
