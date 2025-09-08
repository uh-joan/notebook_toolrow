"""Create source_refs table for Toolrow MCP integration

Revision ID: 20
Revises: 19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20"
down_revision = "19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema - create source_refs table."""
    
    # Create source_refs table
    op.create_table(
        'source_refs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('canonical_id', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('uri', sa.String(), nullable=True),
        sa.Column('params', postgresql.JSONB(), nullable=True),
        sa.Column('artifacts', postgresql.JSONB(), nullable=True),
        sa.Column('ttl_sec', sa.Integer(), default=86400, nullable=True),
        sa.Column('last_run', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('hash', sa.String(), nullable=True),
        sa.Column('provenance', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    # Add check constraint for mode
    op.create_check_constraint(
        'ck_source_refs_mode',
        'source_refs',
        "mode IN ('live', 'snapshot')"
    )
    
    # Create indexes
    op.create_index('ix_source_refs_provider', 'source_refs', ['provider'])
    op.create_index('ix_source_refs_kind', 'source_refs', ['kind'])
    op.create_index('ix_source_refs_canonical_id', 'source_refs', ['canonical_id'])
    op.create_index('ix_source_refs_hash', 'source_refs', ['hash'])
    op.create_index('ix_source_refs_created_at', 'source_refs', ['created_at'])


def downgrade() -> None:
    """Downgrade schema - drop source_refs table."""
    op.drop_table('source_refs')
