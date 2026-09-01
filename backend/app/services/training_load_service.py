from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from operator import attrgetter
from uuid import UUID

from app.database import DbSession
from app.models import CanonicalWorkout, ExerciseDefinition, HealthScore, StrengthEffort
from app.repositories.training_load_repository import TrainingLoadRepository
from app.schemas.training_load import (
    HealthScoreContext,
    LoadMetricComparison,
    MuscleGroupLoad,
    TrainingLoadResponse,
    TrainingPeriodSummary,
)
from app.services.canonical_workout_service import canonical_workout_service
from app.services.performance_record_service import STRENGTH_ALGORITHM_VERSION


@dataclass(frozen=True)
class _PeriodFacts:
    summary: TrainingPeriodSummary
    workout_duration_minutes: Decimal
    strength_volume_kg: Decimal
    running_distance_km: Decimal


@dataclass
class _MuscleFacts:
    current_sets: int = 0
    previous_sets: int = 0
    current_sessions: set[UUID] = field(default_factory=set)
    previous_sessions: set[UUID] = field(default_factory=set)
    current_volume: Decimal = Decimal(0)
    previous_volume: Decimal = Decimal(0)


class TrainingLoadService:
    SCORE_CATEGORIES = {"sleep", "recovery", "readiness", "resilience", "body_battery", "strain"}

    def __init__(self) -> None:
        self.repository = TrainingLoadRepository()

    @staticmethod
    def _percent_change(current: Decimal, previous: Decimal) -> Decimal | None:
        if previous == 0:
            return None
        return ((current - previous) / previous * Decimal(100)).quantize(Decimal("0.1"))

    @staticmethod
    def _period_facts(
        workouts: list[CanonicalWorkout],
        effort_contexts: list[tuple[StrengthEffort, ExerciseDefinition]],
        running_distances: dict[UUID, Decimal],
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> _PeriodFacts:
        duration_minutes = sum(
            (
                Decimal(str(max(0, (item.end_datetime - item.start_datetime).total_seconds()))) / Decimal(60)
                for item in workouts
            ),
            Decimal(0),
        )
        strength_sessions = sum(item.workout_type == "strength_training" for item in workouts)
        running_sessions = sum(item.workout_type == "running" for item in workouts)
        strength_volume = sum((effort.volume_kg for effort, _ in effort_contexts), Decimal(0))
        running_distance = sum((running_distances.get(item.id, Decimal(0)) for item in workouts), Decimal(0)) / Decimal(
            1000
        )
        summary = TrainingPeriodSummary(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            workouts=len(workouts),
            total_duration_minutes=duration_minutes.quantize(Decimal("0.1")),
            strength_sessions=strength_sessions,
            running_sessions=running_sessions,
            other_sessions=len(workouts) - strength_sessions - running_sessions,
            strength_work_sets=len(effort_contexts),
            strength_volume_kg=strength_volume.quantize(Decimal("0.1")),
            running_distance_km=running_distance.quantize(Decimal("0.01")),
        )
        return _PeriodFacts(
            summary=summary,
            workout_duration_minutes=summary.total_duration_minutes,
            strength_volume_kg=summary.strength_volume_kg,
            running_distance_km=summary.running_distance_km,
        )

    @staticmethod
    def _direction(current: Decimal, baseline: Decimal) -> tuple[str, Decimal | None]:
        if baseline <= 0:
            return ("new_load" if current > 0 else "no_load"), None
        ratio = (current / baseline).quantize(Decimal("0.01"))
        if ratio > Decimal("1.5"):
            return "spike", ratio
        if ratio > Decimal("1.1"):
            return "above_baseline", ratio
        if ratio < Decimal("0.8"):
            return "below_baseline", ratio
        return "within_baseline", ratio

    def _comparison(
        self,
        metric: str,
        unit: str,
        current: Decimal,
        previous: Decimal,
        baseline_total: Decimal,
        window_days: int,
        baseline_days: int,
    ) -> LoadMetricComparison:
        baseline = (baseline_total / Decimal(baseline_days) * Decimal(window_days)).quantize(Decimal("0.01"))
        direction, ratio = self._direction(current, baseline)
        return LoadMetricComparison(
            metric=metric,
            unit=unit,
            current=current,
            previous=previous,
            baseline_window_average=baseline,
            current_vs_previous_percent=self._percent_change(current, previous),
            recent_to_baseline_ratio=ratio,
            direction=direction,
        )

    @staticmethod
    def _preferred_scores(scores: list[HealthScore], priorities: dict[object, int]) -> list[HealthScore]:
        selected: dict[tuple[object, object], HealthScore] = {}
        for score in scores:
            key = (score.recorded_at.date(), score.category)
            current = selected.get(key)
            if current is None or priorities.get(score.provider, 99) < priorities.get(current.provider, 99):
                selected[key] = score
        return sorted(selected.values(), key=lambda item: item.recorded_at)

    @staticmethod
    def _average(scores: list[HealthScore]) -> Decimal | None:
        values = [Decimal(score.value) for score in scores if score.value is not None]
        if not values:
            return None
        return (sum(values, Decimal(0)) / Decimal(len(values))).quantize(Decimal("0.1"))

    def get_training_load(
        self,
        db: DbSession,
        user_id: UUID,
        *,
        window_days: int = 7,
        baseline_days: int = 28,
        generated_at: datetime | None = None,
    ) -> TrainingLoadResponse:
        now = generated_at or datetime.now(timezone.utc)
        current_start = now - timedelta(days=window_days)
        previous_start = current_start - timedelta(days=window_days)
        baseline_start = current_start - timedelta(days=baseline_days)
        data_start = min(previous_start, baseline_start)

        workouts = self.repository.list_workouts(db, user_id, data_start, now)
        effort_contexts = self.repository.list_strength_efforts(
            db,
            user_id,
            STRENGTH_ALGORITHM_VERSION,
            data_start,
            now,
        )
        running_distances = {}
        for workout in workouts:
            if workout.workout_type != "running":
                continue
            response = canonical_workout_service.get_response(db, workout.id, user_id)
            if response is not None and response.distance_meters is not None:
                running_distances[workout.id] = Decimal(str(response.distance_meters))

        def period(start: datetime, end: datetime) -> _PeriodFacts:
            return self._period_facts(
                [item for item in workouts if start <= item.start_datetime < end],
                [(effort, definition) for effort, definition in effort_contexts if start <= effort.performed_at < end],
                running_distances,
                start,
                end,
            )

        current = period(current_start, now)
        previous = period(previous_start, current_start)
        baseline = period(baseline_start, current_start)
        metrics = [
            self._comparison(
                "workout_duration",
                "minutes",
                current.workout_duration_minutes,
                previous.workout_duration_minutes,
                baseline.workout_duration_minutes,
                window_days,
                baseline_days,
            ),
            self._comparison(
                "strength_volume",
                "kg",
                current.strength_volume_kg,
                previous.strength_volume_kg,
                baseline.strength_volume_kg,
                window_days,
                baseline_days,
            ),
            self._comparison(
                "running_distance",
                "km",
                current.running_distance_km,
                previous.running_distance_km,
                baseline.running_distance_km,
                window_days,
                baseline_days,
            ),
        ]

        muscle_facts: dict[str, _MuscleFacts] = defaultdict(_MuscleFacts)
        for effort, definition in effort_contexts:
            if effort.performed_at < previous_start:
                continue
            group = definition.primary_muscle_group or "unspecified"
            facts = muscle_facts[group]
            if effort.performed_at >= current_start:
                facts.current_sets += 1
                facts.current_sessions.add(effort.canonical_workout_id)
                facts.current_volume += effort.volume_kg
            else:
                facts.previous_sets += 1
                facts.previous_sessions.add(effort.canonical_workout_id)
                facts.previous_volume += effort.volume_kg

        muscle_groups: list[MuscleGroupLoad] = []
        for group, facts in muscle_facts.items():
            muscle_groups.append(
                MuscleGroupLoad(
                    muscle_group=group,
                    current_work_sets=facts.current_sets,
                    previous_work_sets=facts.previous_sets,
                    current_sessions=len(facts.current_sessions),
                    previous_sessions=len(facts.previous_sessions),
                    current_volume_kg=facts.current_volume.quantize(Decimal("0.1")),
                    previous_volume_kg=facts.previous_volume.quantize(Decimal("0.1")),
                    volume_change_percent=self._percent_change(facts.current_volume, facts.previous_volume),
                )
            )

        priorities = self.repository.provider_priorities(db)
        scores = self._preferred_scores(
            self.repository.list_health_scores(db, user_id, previous_start, now),
            priorities,
        )
        score_groups: dict[str, list[HealthScore]] = defaultdict(list)
        for score in scores:
            category = getattr(score.category, "value", str(score.category))
            if category in self.SCORE_CATEGORIES:
                score_groups[category].append(score)
        health_scores: list[HealthScoreContext] = []
        for category, category_scores in score_groups.items():
            current_scores = [item for item in category_scores if item.recorded_at >= current_start]
            previous_scores = [item for item in category_scores if item.recorded_at < current_start]
            latest = current_scores[-1] if current_scores else category_scores[-1]
            current_average = self._average(current_scores)
            previous_average = self._average(previous_scores)
            health_scores.append(
                HealthScoreContext(
                    category=category,
                    current_observations=len(current_scores),
                    previous_observations=len(previous_scores),
                    latest_value=Decimal(latest.value) if latest.value is not None else None,
                    latest_at=latest.recorded_at,
                    latest_provider=getattr(latest.provider, "value", str(latest.provider)),
                    current_average=current_average,
                    previous_average=previous_average,
                    change=(current_average - previous_average)
                    if current_average is not None and previous_average is not None
                    else None,
                )
            )

        muscle_groups.sort(key=attrgetter("muscle_group"))
        muscle_groups.sort(key=attrgetter("current_work_sets"), reverse=True)
        health_scores.sort(key=attrgetter("category"))
        return TrainingLoadResponse(
            user_id=user_id,
            generated_at=now,
            window_days=window_days,
            baseline_days=baseline_days,
            current_period=current.summary,
            previous_period=previous.summary,
            metrics=metrics,
            muscle_groups=muscle_groups,
            health_scores=health_scores,
            interpretation_notes=[
                "Strength volume is the sum of eligible external-load work sets and is not comparable across athletes.",
                "Recent-to-baseline ratios describe workload change; they are not injury-risk predictions.",
                "Health scores are contextual signals and do not establish that training caused a change.",
            ],
        )


training_load_service = TrainingLoadService()
