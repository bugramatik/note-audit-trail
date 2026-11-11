# Note Audit Trail

Append-only change history for every note, with a field-level diff and a one-call restore.

<img src="screenshots/1.png" alt="Note history screen showing a timeline of revisions with a field-level diff and a restore button" width="800">

## Why

A notes service only ever holds the current row, so the question "what did this note look like before the edit" has no answer. Soft deletes record that a note is gone but not who changed the title or when the tags moved. People who keep notes for compliance, support handovers or shared documentation need to read a record back at any point in time, and rebuilding that from application logs is guesswork. Note Audit Trail puts a small, boring history table in front of every write so any earlier version can be listed and restored.

## How it works

Every write to a note goes through the notes router, which calls the CRUD layer and then records a revision. A revision holds the full snapshot of the note as JSON, the field-level diff against the previous revision, the action that produced it and the user who made it. The history router reads those rows back and can copy any one of them onto the live note.

```mermaid
flowchart LR
    client["Vue client"] --> api["FastAPI app"]
    api --> notes["Notes router"]
    notes --> crud["CRUD layer"]
    crud --> db[("PostgreSQL")]
    notes --> rev["Revision recorder"]
    rev --> db
    api --> hist["History router"]
    hist --> rev
    hist --> crud
    mig["Alembic migrations"] --> db
```

The feature added on top of the base application is the revision recorder and the history router. `record_revision` in `src/app/api/revisions.py` builds the snapshot and diff with `snapshot` and `diff` and inserts one row into `note_revisions` in the same transaction as the note write, so a note never changes without its history row. `list_revisions` returns a note's history newest first, and `get_revision` fetches one row scoped to its owner. `restore_revision` loads the chosen revision, clears its `is_deleted` flag, writes the snapshot back through `crud.put`, then records the restore as a new revision with the pre-restore note as its `before`, so the history stays append-only. The notes routes call the recorder after create, update and delete, and `src/app/main.py` mounts the history router under the same `/notes` prefix, which serves `GET /notes/{id}/history` and `POST /notes/{id}/history/{revision_id}/restore`.

## Key decisions

- Revisions store the whole note as JSON rather than a column-per-field shadow table. Reading an old version is one row lookup and adding a field to notes needs no migration, at the cost of some duplicated storage per revision.
- The diff is computed at write time and stored beside the snapshot. Listing history never has to load two snapshots and compare them, but the diff format is fixed once written.
- Restore writes through the normal update path and then records a new revision instead of deleting later rows. History stays append-only and auditable, at the cost of a longer table.
- The history table is written in the same transaction as the note change, so a failed write leaves no orphan revision and a slow insert adds to the request's latency.

## Tech stack

- Python 3.13, FastAPI, Uvicorn
- SQLAlchemy 2.0 with asyncpg, Alembic migrations
- PostgreSQL 14
- Pydantic v2 and pydantic-settings
- pytest and httpx for the test suite
- Docker and Docker Compose
- Vue 3 and Vite for the optional client

## Quick start

Prerequisites: Docker with Compose, or Python 3.13 and PostgreSQL 14 for a local run.

```bash
docker-compose up -d --build
```

The API is then on `http://localhost:8002`, its OpenAPI docs on `http://localhost:8002/docs`, and the Vue client on `http://localhost:5173`. The container entrypoint runs the Alembic migrations before Uvicorn starts.

To run the tests inside the image:

```bash
docker-compose exec web pytest src -v
```

| Variable | What it sets | Default |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL connection string used by the engine and Alembic | `postgresql://hello_fastapi:hello_fastapi@localhost/hello_fastapi_dev` |
| `SECRET_KEY` | Key used to sign JWT access tokens | `your-secret-key-for-jwt-change-this-in-production` |
| `ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Lifetime of an access token | `30` |
| `ALLOWED_ORIGINS` | Comma-separated origins allowed by CORS | `http://localhost,http://localhost:8080,http://localhost:5173` |
| `ENVIRONMENT` | Environment name reported by the app | `development` |
| `DB_POOL_SIZE` | SQLAlchemy connection pool size | `5` |
| `DB_MAX_OVERFLOW` | Extra connections allowed above the pool size | `10` |

## Usage

List the history of a note, then restore an earlier revision:

```bash
curl -s http://localhost:8002/notes/1/history -H "Authorization: Bearer $TOKEN"
```

```json
[
  {
    "id": 4,
    "note_id": 1,
    "revision": 3,
    "action": "update",
    "changed_by": 1,
    "created_date": "2026-02-11T09:14:02",
    "diff": {"title": {"from": "Release checklist", "to": "Release checklist v2"}}
  },
  {
    "id": 3,
    "note_id": 1,
    "revision": 2,
    "action": "update",
    "changed_by": 1,
    "created_date": "2026-02-10T16:40:51",
    "diff": {"tags": {"from": ["release"], "to": ["release", "ops"]}}
  }
]
```

```bash
curl -s -X POST http://localhost:8002/notes/1/history/3/restore -H "Authorization: Bearer $TOKEN"
```

The restore returns the note with the title and tags of revision 2 and appends a new revision with action `restore`.

## Project structure

```text
src/
  app/
    api/        notes, history, revisions, crud, models, auth
    db.py       async engine and session
    main.py     app factory, routers, CORS
  migrations/   Alembic environment and versions
  tests/        pytest suite for auth, notes, history and ping
vue-client/     optional Vue 3 client
docker-compose.yml
```

## Limitations

- History is kept forever; there is no retention policy or archival job yet.
- Restore works one note at a time, with no bulk rollback across related notes.
- The diff covers top-level fields only, so a change inside a nested structure shows as a whole-value replacement.
- The history endpoints are authenticated but not role-gated, so any owner can restore their own notes only.

## License

MIT. The project builds on [Fast-Api-example](https://github.com/KenMwaura1/Fast-Api-example) by KenMwaura1, kept under its original MIT licence.
