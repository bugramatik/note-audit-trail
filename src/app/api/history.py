from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.api import crud, revisions
from app.api.dependencies import get_current_active_user
from app.api.models import ErrorResponse, NoteDB, RevisionDB
from app.db import get_db

router = APIRouter()


@router.get(
    "/{id}/history",
    response_model=List[RevisionDB],
    responses={404: {"model": ErrorResponse}, 422: {"description": "Invalid note ID"}},
)
async def read_history(
    id: int = Path(..., gt=0, description="Note ID"),
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """List every recorded revision of a note, newest first."""
    note = await crud.get(session, id)
    if not note or note["owner_id"] != current_user.id:
        raise HTTPException(status_code=404, detail=f"Note with id {id} not found")
    return await revisions.list_revisions(session, id, current_user.id)


@router.post(
    "/{id}/history/{revision_id}/restore",
    response_model=NoteDB,
    responses={404: {"model": ErrorResponse}, 422: {"description": "Invalid ID"}},
)
async def restore(
    id: int = Path(..., gt=0, description="Note ID"),
    revision_id: int = Path(..., gt=0, description="Revision ID"),
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Restore a note to the state held by one of its revisions."""
    note = await crud.get(session, id)
    if not note or note["owner_id"] != current_user.id:
        raise HTTPException(status_code=404, detail=f"Note with id {id} not found")
    restored = await revisions.restore_revision(session, id, revision_id, current_user.id)
    if restored is None:
        raise HTTPException(
            status_code=404,
            detail=f"Revision {revision_id} of note {id} not found",
        )
    return restored
