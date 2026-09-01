from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from operator import attrgetter
from uuid import UUID

from app.database import DbSession
from app.models import ExerciseDefinition, RunningEffort, StrengthEffort
from app.repositories.performance_record_repository import PerformanceRecordRepository
from app.schemas.performance_records import (
    CoachingProgressResponse,
    RunningProgressInsight,
    StrengthProgressInsight,
)
from app.services.performance_record_service import RUNNING_ALGORITHM_VERSION, STRENGTH_ALGORITHM_VERSION


@dataclass(frozen=True)
class _StrengthSession:
    performed_at: datetime
    estimated_one_rep_max_kg: Decimal
    top_load_kg: Decimal
    volume_kg: Decimal


class CoachingProgressService:
    def __init__(self) -> None:
        self.repository = PerformanceRecordRepository()

    @staticmethod
    def _percent(change: Decimal, baseline: Decimal) -> Decimal | None:
        if baseline == 0:
            return None
        return (change / baseline * Decimal(100)).quantize(Decimal("0.1"))

    @staticmethod
    def _status(values: list[Decimal], *, higher_is_better: bool, plateau_attempts: int) -> tuple[str, int]:
        if len(values) == 1:
            return "new", 0
        best = max(values) if higher_is_better else min(values)
        best_index = max(index for index, value in enumerate(values) if value == best)
        attempts_since_best = len(values) - best_index - 1
        prior_values = values[:best_index]
        previous_best = (max(prior_values) if higher_is_better else min(prior_values)) if prior_values else None
        is_new_best = previous_best is not None and (best > previous_best if higher_is_better else best < previous_best)
        if is_new_best and attempts_since_best <= 1:
            return "progressing", attempts_since_best
        if attempts_since_best >= plateau_attempts:
            return "plateau", attempts_since_best
        return "maintaining", attempts_since_best

    @staticmethod
    def _average(values: list[Decimal]) -> Decimal | None:
        if not values:
            return None
        return (sum(values, Decimal(0)) / Decimal(len(values))).quantize(Decimal("0.001"))

    @staticmethod
    def _strength_sessions(efforts: list[StrengthEffort]) -> list[_StrengthSession]:
        grouped: dict[UUID, list[StrengthEffort]] = defaultdict(list)
        for effort in efforts:
            grouped[effort.canonical_workout_id].append(effort)
        sessions = []
        for session_efforts in grouped.values():
            eligible = [item for item in session_efforts if item.estimated_one_rep_max_kg is not None]
            if not eligible:
                continue
            sessions.append(
                _StrengthSession(
                    performed_at=min(item.performed_at for item in eligible),
                    estimated_one_rep_max_kg=max(
                        item.estimated_one_rep_max_kg for item in eligible if item.estimated_one_rep_max_kg is not None
                    ),
                    top_load_kg=max(item.load_kg for item in eligible),
                    volume_kg=sum((item.volume_kg for item in eligible), Decimal(0)),
                )
            )
        return sorted(sessions, key=lambda item: item.performed_at)

    def get_progress(
        self,
        db: DbSession,
        user_id: UUID,
        *,
        exercise_definition_id: UUID | None = None,
        distance_meters: int | None = None,
        window_days: int = 42,
        plateau_attempts: int = 3,
        generated_at: datetime | None = None,
    ) -> CoachingProgressResponse:
        now = generated_at or datetime.now(timezone.utc)
        recent_start = now - timedelta(days=window_days)
        previous_start = recent_start - timedelta(days=window_days)

        strength_contexts = self.repository.list_strength_effort_contexts_for_user(
            db,
            user_id,
            STRENGTH_ALGORITHM_VERSION,
            exercise_definition_id,
        )
        strength_groups: dict[UUID, tuple[ExerciseDefinition, list[StrengthEffort]]] = {}
        for effort, definition in strength_contexts:
            strength_groups.setdefault(definition.id, (definition, []))[1].append(effort)

        strength: list[StrengthProgressInsight] = []
        for definition, efforts in strength_groups.values():
            sessions = self._strength_sessions(efforts)
            if not sessions:
                continue
            values = [item.estimated_one_rep_max_kg for item in sessions]
            status, sessions_since_best = self._status(
                values,
                higher_is_better=True,
                plateau_attempts=plateau_attempts,
            )
            personal_best = max(values)
            best_session = next(item for item in reversed(sessions) if item.estimated_one_rep_max_kg == personal_best)
            first = sessions[0]
            latest = sessions[-1]
            change = latest.estimated_one_rep_max_kg - first.estimated_one_rep_max_kg
            recent_volumes = [item.volume_kg for item in sessions if item.performed_at >= recent_start]
            previous_volumes = [
                item.volume_kg for item in sessions if previous_start <= item.performed_at < recent_start
            ]
            recent_average = self._average(recent_volumes)
            previous_average = self._average(previous_volumes)
            volume_change = (
                self._percent(recent_average - previous_average, previous_average)
                if recent_average is not None and previous_average is not None
                else None
            )
            if not recent_volumes:
                status = "inactive"
            strength.append(
                StrengthProgressInsight(
                    exercise_id=definition.id,
                    exercise_name=definition.name,
                    status=status,
                    sessions=len(sessions),
                    sessions_in_window=len(recent_volumes),
                    latest_performed_at=latest.performed_at,
                    latest_estimated_one_rep_max_kg=latest.estimated_one_rep_max_kg,
                    personal_best_estimated_one_rep_max_kg=personal_best,
                    personal_best_at=best_session.performed_at,
                    estimated_one_rep_max_change_from_first_kg=change,
                    estimated_one_rep_max_change_percent=self._percent(
                        change,
                        first.estimated_one_rep_max_kg,
                    ),
                    sessions_since_best=sessions_since_best,
                    days_since_best=max(0, (now - best_session.performed_at).days),
                    latest_top_load_kg=latest.top_load_kg,
                    latest_volume_kg=latest.volume_kg,
                    recent_average_volume_kg=recent_average,
                    previous_average_volume_kg=previous_average,
                    volume_change_percent=volume_change,
                )
            )

        running_efforts = self.repository.list_running_efforts_for_user(
            db,
            user_id,
            RUNNING_ALGORITHM_VERSION,
            distance_meters,
        )
        running_groups: dict[int, list[RunningEffort]] = defaultdict(list)
        for effort in running_efforts:
            running_groups[effort.target_distance_meters].append(effort)

        running: list[RunningProgressInsight] = []
        for distance, efforts in running_groups.items():
            values = [item.elapsed_seconds for item in efforts]
            status, attempts_since_best = self._status(
                values,
                higher_is_better=False,
                plateau_attempts=plateau_attempts,
            )
            personal_best = min(values)
            best_effort = next(item for item in reversed(efforts) if item.elapsed_seconds == personal_best)
            first = efforts[0]
            latest = efforts[-1]
            seconds_improved = first.elapsed_seconds - latest.elapsed_seconds
            attempts_in_window = sum(item.performed_at >= recent_start for item in efforts)
            if attempts_in_window == 0:
                status = "inactive"
            running.append(
                RunningProgressInsight(
                    distance_meters=distance,
                    status=status,
                    attempts=len(efforts),
                    attempts_in_window=attempts_in_window,
                    latest_performed_at=latest.performed_at,
                    latest_time_seconds=latest.elapsed_seconds,
                    personal_best_time_seconds=personal_best,
                    personal_best_at=best_effort.performed_at,
                    seconds_improved_from_first=seconds_improved,
                    improvement_percent=self._percent(seconds_improved, first.elapsed_seconds),
                    attempts_since_best=attempts_since_best,
                    days_since_best=max(0, (now - best_effort.performed_at).days),
                    calculation_method=best_effort.calculation_method,
                    confidence=best_effort.confidence,
                )
            )

        return CoachingProgressResponse(
            user_id=user_id,
            generated_at=now,
            window_days=window_days,
            plateau_attempts=plateau_attempts,
            strength=sorted(strength, key=attrgetter("exercise_name")),
            running=sorted(running, key=attrgetter("distance_meters")),
        )


coaching_progress_service = CoachingProgressService()
