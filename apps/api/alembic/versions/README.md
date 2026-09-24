# Migration revisions

`0001_empty_baseline` records the TWF-1.3 empty production schema. Only Alembic's
version table is created. No business tables exist. Future schema changes extend
this history and register models with `twf.infrastructure.database.Base.metadata`.
Never create application tables or auto-run migrations at API startup.
