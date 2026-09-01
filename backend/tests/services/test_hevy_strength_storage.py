from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from app.schemas.providers.hevy import HevyExerciseTemplate
from app.services.providers.hevy.strength_storage import enrich_exercise_definitions

USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def test_hevy_templates_enrich_existing_exercise_definitions() -> None:
    definition = SimpleNamespace(
        provider_exercise_id="bench-template",
        equipment=None,
        primary_muscle_group=None,
        is_custom=False,
    )
    template = HevyExerciseTemplate(
        id="bench-template",
        title="Bench Press (Barbell)",
        type="weight_reps",
        primary_muscle_group="chest",
        secondary_muscle_groups=["triceps", "shoulders"],
        equipment_category="barbell",
        is_custom=False,
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [definition]

    updated = enrich_exercise_definitions(db, USER_ID, {template.id: template})

    assert updated == 1
    assert definition.primary_muscle_group == "chest"
    assert definition.equipment == "barbell"
    db.flush.assert_called_once()
