"""Create notebook_sources table for Toolrow MCP integration

Revision ID: 21
Revises: 20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "21"
down_revision = "20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema - create notebook_sources table."""
    
    # Create notebook_sources table (linking search spaces to source_refs)
    op.create_table(
        'notebook_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('search_space_id', sa.Integer(), nullable=False),  # Using search_space as "notebook"
        sa.Column('source_ref_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('added_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    # Create foreign key constraints
    op.create_foreign_key(
        'fk_notebook_sources_search_space_id',
        'notebook_sources',
        'searchspaces',
        ['search_space_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    op.create_foreign_key(
        'fk_notebook_sources_source_ref_id',
        'notebook_sources',
        'source_refs',
        ['source_ref_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    op.create_foreign_key(
        'fk_notebook_sources_added_by',
        'notebook_sources',
        'user',
        ['added_by'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Create indexes
    op.create_index('ix_notebook_sources_search_space_id', 'notebook_sources', ['search_space_id'])
    op.create_index('ix_notebook_sources_source_ref_id', 'notebook_sources', ['source_ref_id'])
    op.create_index('ix_notebook_sources_created_at', 'notebook_sources', ['created_at'])
    
    # Create unique constraint to prevent duplicate sources in the same search space
    op.create_unique_constraint(
        'uq_notebook_sources_search_space_source',
        'notebook_sources',
        ['search_space_id', 'source_ref_id']
    )


def downgrade() -> None:
    """Downgrade schema - drop notebook_sources table."""
    op.drop_table('notebook_sources')
