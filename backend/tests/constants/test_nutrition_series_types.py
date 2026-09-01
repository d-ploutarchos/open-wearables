from app.constants.series_types.sdk.metric_types import get_series_type_from_metric_type
from app.constants.webhooks.events import SERIES_TYPE_TO_GRANULAR_EVENT, SERIES_TYPE_TO_GROUP_EVENT
from app.schemas.enums import SeriesType, get_series_type_id, get_series_type_unit
from app.schemas.webhooks.event_types import WebhookEventType


def test_apple_nutrition_metrics_map_to_series_types() -> None:
    assert (
        get_series_type_from_metric_type("HKQuantityTypeIdentifierDietaryEnergyConsumed")
        is SeriesType.dietary_energy_consumed
    )
    assert get_series_type_from_metric_type("HKQuantityTypeIdentifierDietaryProtein") is SeriesType.dietary_protein
    assert get_series_type_id(SeriesType.dietary_energy_consumed) == 300
    assert get_series_type_unit(SeriesType.dietary_carbohydrates) == "g"


def test_nutrition_series_emit_group_and_granular_events() -> None:
    assert SERIES_TYPE_TO_GROUP_EVENT["dietary_energy_consumed"] is WebhookEventType.NUTRITION_CREATED
    assert SERIES_TYPE_TO_GRANULAR_EVENT["dietary_protein"] is WebhookEventType.SERIES_DIETARY_PROTEIN
