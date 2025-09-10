"""add_discovered_source_to_document_type_enum

Revision ID: a3f6b27dc3a0
Revises: 4548830e47ce
Create Date: 2025-09-09 16:42:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3f6b27dc3a0'
down_revision: Union[str, None] = '4548830e47ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add DISCOVERED_SOURCE to DocumentType enum."""
    # Add the new enum value to DocumentType
    op.execute("ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'DISCOVERED_SOURCE'")


def downgrade() -> None:
    """Remove DISCOVERED_SOURCE from DocumentType enum."""
    # Note: PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum type, which is complex
    # For now, we'll leave the enum value in place during downgrade
    pass