"""add summoners table

Revision ID: 68504509edb2
Revises: 2115c95c1b7c
Create Date: 2025-08-11 11:28:17.737644

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '68504509edb2'
down_revision: Union[str, Sequence[str], None] = '2115c95c1b7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Ensure schema exists (idempotent)
    op.execute(sa.text('CREATE SCHEMA IF NOT EXISTS "porygon"'))
    # Create only the new summoners table in this revision
    op.create_table('summoners',
    sa.Column('puuid', sa.String(length=78), nullable=False),
    sa.Column('discord_id', sa.String(length=32), nullable=True),
    sa.Column('profile_icon_id', sa.BigInteger(), nullable=True),
    sa.Column('revision_date', sa.BigInteger(), nullable=True),
    sa.Column('summoner_level', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('puuid'),
    sa.UniqueConstraint('puuid'),
    schema='porygon'
    )
    # ### end commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # Only drop the summoners table created in this revision
    op.drop_table('summoners', schema='porygon')
    # ### end commands ###
