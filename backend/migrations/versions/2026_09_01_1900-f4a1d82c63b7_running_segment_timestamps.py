"""add measured running segment timestamps

Revision ID: f4a1d82c63b7
Revises: e8f2c73b91a4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a1d82c63b7"
down_revision: Union[str, None] = "e8f2c73b91a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "running_effort",
        sa.Column("segment_start_datetime", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "running_effort",
        sa.Column("segment_end_datetime", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("running_effort", "segment_end_datetime")
    op.drop_column("running_effort", "segment_start_datetime")
