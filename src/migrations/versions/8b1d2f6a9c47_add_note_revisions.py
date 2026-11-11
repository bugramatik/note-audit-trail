"""Add note revisions

Revision ID: 8b1d2f6a9c47
Revises: 3fcc41254e35
Create Date: 2026-05-02 09:14:03.221904

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b1d2f6a9c47"
down_revision: Union[str, Sequence[str], None] = "3fcc41254e35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the append-only note_revisions table."""
    op.create_table(
        "note_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("diff", sa.JSON(), nullable=False),
        sa.Column("created_date", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_note_revisions_note_id"), "note_revisions", ["note_id"], unique=False
    )
    op.create_index(
        op.f("ix_note_revisions_owner_id"),
        "note_revisions",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_note_revisions_created_date"),
        "note_revisions",
        ["created_date"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the note_revisions table."""
    op.drop_index(op.f("ix_note_revisions_created_date"), table_name="note_revisions")
    op.drop_index(op.f("ix_note_revisions_owner_id"), table_name="note_revisions")
    op.drop_index(op.f("ix_note_revisions_note_id"), table_name="note_revisions")
    op.drop_table("note_revisions")
