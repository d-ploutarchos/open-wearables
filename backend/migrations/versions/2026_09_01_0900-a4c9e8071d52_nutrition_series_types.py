"""nutrition series types

Revision ID: a4c9e8071d52
Revises: dc5ac28c4b94
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4c9e8071d52"
down_revision: Union[str, None] = "dc5ac28c4b94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NUTRITION_SERIES_TYPES = (
    (300, "dietary_energy_consumed", "kcal"),
    (301, "dietary_carbohydrates", "g"),
    (302, "dietary_protein", "g"),
    (303, "dietary_fat_total", "g"),
    (304, "dietary_water", "mL"),
)


def upgrade() -> None:
    for type_id, code, unit in _NUTRITION_SERIES_TYPES:
        op.execute(
            "INSERT INTO series_type_definition (id, code, unit) "
            f"VALUES ({type_id}, '{code}', '{unit}') "
            "ON CONFLICT (id) DO UPDATE SET code = EXCLUDED.code, unit = EXCLUDED.unit"
        )


def downgrade() -> None:
    op.execute("DELETE FROM series_type_definition WHERE id BETWEEN 300 AND 304")
