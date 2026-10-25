"""initial_schema

Revision ID: 704170dc69b0
Revises:
Create Date: 2026-10-24

Bootstrap migration: creates the full SQLAlchemy metadata on an empty database.
Later revisions should be incremental (alembic revision --autogenerate).
"""

from typing import Sequence, Union

from alembic import op

from app.core.database import Base
import app.models  # noqa: F401

revision: str = "704170dc69b0"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
