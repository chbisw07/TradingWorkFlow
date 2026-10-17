from __future__ import annotations

import os

from sqlalchemy import create_engine, text


OBJECTS = (
    "manual_order_previews",
    "twf_dispatch_attempts",
    "twf_order_public_ids",
    "twf_public_id_counters",
    "twf_queue_dispatch_policies",
    "twf_queue_entries",
    "twf_queue_events",
    "twf_queue_policy_events",
)


engine = create_engine(os.environ["TWF_DATABASE_URL"])
with engine.connect() as connection:
    print("current_user", connection.execute(text("SELECT current_user")).scalar_one())
    rows = connection.execute(
        text(
            """
            SELECT c.relname,
                   pg_get_userbyid(c.relowner) AS owner,
                   has_table_privilege(current_user, c.oid, 'SELECT') AS can_select,
                   has_table_privilege(current_user, c.oid, 'INSERT') AS can_insert,
                   has_table_privilege(current_user, c.oid, 'UPDATE') AS can_update,
                   has_table_privilege(current_user, c.oid, 'DELETE') AS can_delete
              FROM pg_class AS c
             WHERE c.relnamespace = 'public'::regnamespace
               AND c.relname = ANY(:objects)
             ORDER BY c.relname
            """
        ),
        {"objects": list(OBJECTS)},
    )
    for row in rows:
        print(*row)
