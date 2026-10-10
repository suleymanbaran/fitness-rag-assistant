"""add users.api_token_hash

Revision ID: 2875a6b0a8bc
Revises: 843b3f2949bb
Create Date: 2026-10-10 11:43:47.515835
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '2875a6b0a8bc'
down_revision: str | None = '843b3f2949bb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('api_token_hash', sa.String(length=64), nullable=True))
    # Same name Postgres gives the constraint when the model's unique=True creates it directly.
    op.create_unique_constraint('users_api_token_hash_key', 'users', ['api_token_hash'])


def downgrade() -> None:
    op.drop_constraint('users_api_token_hash_key', 'users', type_='unique')
    op.drop_column('users', 'api_token_hash')
