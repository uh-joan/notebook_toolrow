"""Add ToolRow settings table for user-specific API tokens

Revision ID: 22
Revises: 21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "22"
down_revision = "bb542acf8975"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema - create toolrow_settings table."""
    
    # Create toolrow_settings table
    op.create_table(
        'toolrow_settings',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('api_token', sa.Text(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('max_calls', sa.Integer(), nullable=False, default=6),
        sa.Column('timeout_ms', sa.Integer(), nullable=False, default=30000),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        # Foreign key to user table
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        
        # Ensure one settings record per user
        sa.UniqueConstraint('user_id', name='uq_toolrow_settings_user_id')
    )
    
    # Create indexes
    op.create_index('ix_toolrow_settings_id', 'toolrow_settings', ['id'])
    op.create_index('ix_toolrow_settings_user_id', 'toolrow_settings', ['user_id'])


def downgrade() -> None:
    """Downgrade schema - drop toolrow_settings table."""
    op.drop_table('toolrow_settings')
