from __future__ import annotations

import os

from sqlalchemy import create_engine, text


engine = create_engine(os.environ["TWF_DATABASE_URL"])
with engine.connect() as connection:
    tables = connection.execute(
        text(
            """
            SELECT relname
              FROM pg_class
             WHERE relnamespace = 'public'::regnamespace
               AND relkind IN ('r', 'p')
             ORDER BY relname
            """
        )
    ).scalars()
    for table in tables:
        quoted = connection.dialect.identifier_preparer.quote(table)
        count, digest = connection.execute(
            text(
                f"""
                SELECT count(*),
                       md5(COALESCE(string_agg(row_hash, '' ORDER BY row_hash COLLATE "C"), ''))
                  FROM (
                        SELECT md5(row_to_json(source_row)::text) AS row_hash
                          FROM public.{quoted} AS source_row
                       ) AS canonical_rows
                """
            )
        ).one()
        print(f"{table}|{count}|{digest}")
