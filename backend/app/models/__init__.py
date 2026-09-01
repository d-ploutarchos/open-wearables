from .api_key import ApiKey
from .application import Application
from .archival_setting import ArchivalSetting
from .canonical_workout import CanonicalWorkout
from .canonical_workout_source import CanonicalWorkoutSource
from .data_point_series import DataPointSeries
from .data_point_series_archive import DataPointSeriesArchive
from .data_source import DataSource
from .developer import Developer
from .device_type_priority import DeviceTypePriority
from .event_record import EventRecord
from .event_record_detail import DetailType, EventRecordDetail
from .exercise_definition import ExerciseDefinition
from .exercise_set import ExerciseSet
from .health_score import HealthScore
from .invitation import Invitation
from .menstrual_cycle_details import MenstrualCycleDetails
from .performance_record import PerformanceRecord, PerformanceRecordHistory
from .personal_record import PersonalRecord
from .provider_priority import ProviderPriority
from .provider_setting import ProviderSetting
from .refresh_token import RefreshToken
from .series_type_definition import SeriesTypeDefinition
from .sleep_details import SleepDetails
from .strength_effort import StrengthEffort
from .user import User
from .user_connection import UserConnection
from .user_invitation_code import UserInvitationCode
from .workout_details import WorkoutDetails
from .workout_exercise import WorkoutExercise

# Single source of truth mapping detail_type -> concrete model, derived from the
# EventRecordDetail subclasses defined above. Adding a new detail model (and
# importing it here, as every model must be for the ORM) registers it automatically.
DETAIL_MODELS: dict[DetailType, type[EventRecordDetail]] = {
    model.detail_type: model for model in EventRecordDetail.__subclasses__()
}

__all__ = [
    "ApiKey",
    "Application",
    "ArchivalSetting",
    "CanonicalWorkout",
    "CanonicalWorkoutSource",
    "Developer",
    "DataSource",
    "DataPointSeriesArchive",
    "DeviceTypePriority",
    "Invitation",
    "ProviderPriority",
    "ProviderSetting",
    "RefreshToken",
    "User",
    "UserConnection",
    "UserInvitationCode",
    "EventRecord",
    "EventRecordDetail",
    "ExerciseDefinition",
    "ExerciseSet",
    "MenstrualCycleDetails",
    "SleepDetails",
    "WorkoutDetails",
    "WorkoutExercise",
    "PersonalRecord",
    "PerformanceRecord",
    "PerformanceRecordHistory",
    "StrengthEffort",
    "DataPointSeries",
    "SeriesTypeDefinition",
    "HealthScore",
    "DetailType",
    "DETAIL_MODELS",
]
