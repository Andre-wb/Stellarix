# `alembic/` — Database Migrations

Alembic-driven schema migrations for the Vortex node database. Runs against both SQLite (dev) and PostgreSQL (prod) — the migration files are dialect-agnostic.

## Files

| File              | Role                                                                          |
| ----------------- | ----------------------------------------------------------------------------- |
| `env.py`          | Migration runner. Pulls `app.base.Base.metadata` as the autogenerate source; resolves the DB URL via `app.config` (same precedence as the running node). |
| `script.py.mako`  | Revision template. Every new migration is generated from this.                |
| `versions/`       | One Python file per migration — monotonic, each file carries a `down_revision` pointer to the previous head. |

The alembic config file (`alembic.ini`) lives at the repo root.

## Common operations

From the repo root, inside the activated venv:

```bash
# Current head on the connected database
alembic current

# Generate a new migration from model diffs
alembic revision --autogenerate -m "add foo column to rooms"

# Apply all pending migrations
alembic upgrade head

# Roll back one step
alembic downgrade -1

# Show migration graph
alembic history --verbose
```

### In production

The node runs `alembic upgrade head` on startup if `AUTO_MIGRATE=true` (default on first install). Operators who pin versions manually can disable this in `config.yaml` and run migrations from a maintenance shell.

## Writing a migration

1. Change the SQLAlchemy model under `app/models/` or `app/models_rooms/`.
2. `alembic revision --autogenerate -m "<short description>"`.
3. Open the generated file under `versions/` — **always review**. Autogen misses:
   - `server_default` → constant defaults
   - enum value renames
   - renamed columns (autogen drops + adds — add `op.alter_column(..., new_column_name=...)` manually)
4. Test the forward migration on a copy of production data.
5. Write a sensible `downgrade()` — even if it just raises `NotImplementedError` with a clear reason.

## Data migrations

Column moves, splits, and backfills live **inside** the migration file using `op.execute()` or a scoped `Session`:

```python
def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE rooms SET kind = 'public' WHERE kind IS NULL"))
```

Do **not** import the ORM model in a migration — models evolve, migrations don't. Use raw `sqlalchemy` `Table`/`sa.text` objects or reflected tables.

## Dialect notes

- **SQLite** does not support `ALTER COLUMN` — alembic batch mode is auto-enabled (`render_as_batch=True` in `env.py`).
- **PostgreSQL** gets the original `ALTER TABLE` statements, which is faster on big tables.

---

## License

Vortex is released under the **Apache License 2.0**.

```
Copyright 2026 Andrey Karavaev, Boris Maltsev

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## Authors

**Boris Maltsev**

[![GitHub](https://img.shields.io/badge/GitHub-BorisMalts-181717?style=flat-square&logo=github)](https://github.com/BorisMalts)

**Andrey Karavaev**

[![GitHub](https://img.shields.io/badge/GitHub-Andre--wb-181717?style=flat-square&logo=github)](https://github.com/Andre-wb)
