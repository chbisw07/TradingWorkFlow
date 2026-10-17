from __future__ import annotations

import os

from sqlalchemy import create_engine, text


engine = create_engine(os.environ["TWF_DATABASE_URL"])
with engine.connect() as connection:
    for row in connection.execute(
        text(
            """
            SELECT c.relkind,
                   c.relname,
                   pg_get_userbyid(c.relowner) AS owner,
                   has_table_privilege('twf_migrator', c.oid, 'SELECT,INSERT,UPDATE,DELETE')
                       AS migrator_dml,
                   has_table_privilege('twf_app', c.oid, 'SELECT') AS app_select,
                   has_table_privilege('twf_app', c.oid, 'INSERT') AS app_insert,
                   has_table_privilege('twf_app', c.oid, 'UPDATE') AS app_update,
                   has_table_privilege('twf_app', c.oid, 'DELETE') AS app_delete
              FROM pg_class AS c
             WHERE c.relnamespace = 'public'::regnamespace
               AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
             ORDER BY c.relkind, c.relname
            """
        )
    ):
        print(*row)
    print("FUNCTIONS")
    for row in connection.execute(
        text(
            """
            SELECT p.proname,
                   pg_get_function_identity_arguments(p.oid),
                   pg_get_userbyid(p.proowner),
                   has_function_privilege('twf_app', p.oid, 'EXECUTE')
              FROM pg_proc AS p
             WHERE p.pronamespace = 'public'::regnamespace
             ORDER BY p.proname
            """
        )
    ):
        print(*row)
    print("TRIGGERS")
    for row in connection.execute(
        text(
            """
            SELECT c.relname, t.tgname, t.tgenabled, p.proname
              FROM pg_trigger AS t
              JOIN pg_class AS c ON c.oid = t.tgrelid
              JOIN pg_proc AS p ON p.oid = t.tgfoid
             WHERE c.relnamespace = 'public'::regnamespace
               AND NOT t.tgisinternal
             ORDER BY c.relname, t.tgname
            """
        )
    ):
        print(*row)
    print("OE4_CONSTRAINTS_AND_INDEXES")
    for row in connection.execute(
        text(
            """
            SELECT 'constraint', c.relname, con.conname, pg_get_constraintdef(con.oid)
              FROM pg_constraint AS con
              JOIN pg_class AS c ON c.oid = con.conrelid
             WHERE c.relnamespace = 'public'::regnamespace
               AND (c.relname LIKE 'twf_%' OR c.relname = 'manual_order_previews')
            UNION ALL
            SELECT 'index', tab.relname, idx.relname, pg_get_indexdef(idx.oid)
              FROM pg_index AS i
              JOIN pg_class AS tab ON tab.oid = i.indrelid
              JOIN pg_class AS idx ON idx.oid = i.indexrelid
             WHERE tab.relnamespace = 'public'::regnamespace
               AND (tab.relname LIKE 'twf_%' OR tab.relname = 'manual_order_previews')
             ORDER BY 1, 2, 3
            """
        )
    ):
        print(*row)
