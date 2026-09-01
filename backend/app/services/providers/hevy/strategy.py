from typing import cast

from app.services.providers.base_strategy import BaseProviderStrategy, ProviderCapabilities, ProviderCoverage
from app.services.providers.templates.base_workouts import BaseWorkoutsTemplate

from .coverage import WORKOUT_FIELDS
from .workouts import hevy_workouts


class HevyStrategy(BaseProviderStrategy):
    def __init__(self) -> None:
        super().__init__()
        # Hevy uses API-key auth rather than BaseWorkoutsTemplate's OAuth helper,
        # but exposes the same provider strategy surface (load_data/detail fetch).
        self.workouts = cast(BaseWorkoutsTemplate, hevy_workouts)

    @property
    def name(self) -> str:
        return "hevy"

    @property
    def display_name(self) -> str:
        return "Hevy"

    @property
    def api_base_url(self) -> str:
        return "https://api.hevyapp.com"

    @property
    def coverage(self) -> ProviderCoverage:
        return ProviderCoverage(workout_fields=WORKOUT_FIELDS)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(rest_pull=True, webhook_ping=True)
