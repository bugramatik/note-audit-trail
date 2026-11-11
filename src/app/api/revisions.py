from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import metadata

# Append-only history for notes. One row per write, holding the full snapshot
# of the note as it looked after the write plus the field-level diff.
note_revisions = Table(
    "note_revisions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("note_id", Integer, ForeignKey("notes.id"), nullable=False, index=True),
    Column("owner_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("action", String(16), nullable=False),
    Column("snapshot", JSON, nullable=False),
    Column("diff", JSON, nullable=False),
    Column("created_date", DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True),
)

TRACKED_FIELDS = ("title", "description", "completed", "tags", "is_deleted")


def snapshot(note: Dict[str, Any]) -> Dict[str, Any]:
    """Copy the tracked fields of a note into a plain JSON-safe dict."""
    return {field: note.get(field) for field in TRACKED_FIELDS}


def diff(before: Optional[Dict[str, Any]], after: Dict[str, Any]) -> Dict[str, Any]:
    """Return {field: {"from": old, "to": new}} for every field that changed."""
    before = before or {}
    changes: Dict[str, Any] = {}
    for field in TRACKED_FIELDS:
        old_value = before.get(field)
        new_value = after.get(field)
        if old_value != new_value:
            changes[field] = {"from": old_value, "to": new_value}
    return changes


async def record_revision(
    session: AsyncSession,
    note: Dict[str, Any],
    action: str,
    before: Optional[Dict[str, Any]] = None,
) -> int:
    """Append one revision row for a note write and return its ID.

    The caller commits; this keeps the revision in the same transaction as the
    note write so a note never changes without its history row.
    """
    after = snapshot(note)
    query = (
        insert(note_revisions)
        .values(
            note_id=note["id"],
            owner_id=note["owner_id"],
            action=action,
            snapshot=after,
            diff=diff(before, after),
            created_date=datetime.now(timezone.utc),
        )
        .returning(note_revisions.c.id)
    )
    result = await session.execute(query)
    return result.scalar()


async def list_revisions(
    session: AsyncSession, note_id: int, owner_id: int
) -> List[Dict[str, Any]]:
    """Return every revision of a note, newest first."""
    query = (
        select(note_revisions)
        .where(
            note_revisions.c.note_id == note_id,
            note_revisions.c.owner_id == owner_id,
        )
        .order_by(note_revisions.c.created_date.desc(), note_revisions.c.id.desc())
    )
    result = await session.execute(query)
    return [dict(row) for row in result.mappings().all()]


async def get_revision(
    session: AsyncSession, note_id: int, revision_id: int, owner_id: int
) -> Optional[Dict[str, Any]]:
    """Fetch a single revision of a note, scoped to its owner."""
    query = select(note_revisions).where(
        note_revisions.c.id == revision_id,
        note_revisions.c.note_id == note_id,
        note_revisions.c.owner_id == owner_id,
    )
    result = await session.execute(query)
    row = result.mappings().first()
    return dict(row) if row else None


async def restore_revision(
    session: AsyncSession, note_id: int, revision_id: int, owner_id: int
) -> Optional[Dict[str, Any]]:
    """Write a revision's snapshot back onto the note and record the restore.

    Returns the restored note, or None when the revision does not exist.
    """
    from app.api import crud

    revision = await get_revision(session, note_id, revision_id, owner_id)
    if revision is None:
        return None

    current = await crud.get(session, note_id)
    if current is None or current["owner_id"] != owner_id:
        return None

    restored = dict(revision["snapshot"])
    restored["is_deleted"] = False
    await crud.put(session, note_id, restored)
    updated = await crud.get(session, note_id)
    await record_revision(session, updated, "restore", before=current)
    await session.commit()
    return updated
