# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class DataTypeCount(BaseModel):
    """Count of records for a specific data type."""

    type: str
    count: int = Field(ge=0)


class TimeRange(BaseModel):
    # startDate is absent when the SDK syncs the full available history (no syncDaysBack
    # limit configured) — both the iOS and Android SDKs omit it in that case.
    startDate: datetime | None = None
    endDate: datetime


class HistoricalDataSyncStartEvent(BaseModel):
    eventType: Literal["historical_data_sync_start"]
    timestamp: datetime
    dataTypeCounts: list[DataTypeCount] = Field(default_factory=list)
    timeRange: TimeRange | None = None


class HistoricalDataTypeSyncEndEvent(BaseModel):
    eventType: Literal["historical_data_type_sync_end"]
    timestamp: datetime
    dataType: str
    success: bool
    recordCount: int | None = None
    durationMs: int | None = None


class DeviceStateEvent(BaseModel):
    eventType: Literal["device_state"]
    timestamp: datetime
    batteryLevel: float | None = Field(None, ge=0.0, le=1.0)
    batteryState: str | None = None
    isLowPowerMode: bool | None = None
    thermalState: str | None = None
    taskType: str | None = None
    availableRamBytes: int | None = None
    totalRamBytes: int | None = None


class BackgroundDeliveryRegistrationEvent(BaseModel):
    """Result of registering one HealthKit type for background delivery."""

    eventType: Literal["background_delivery_registration"]
    timestamp: datetime
    dataType: str
    success: bool
    error: str | None = None


class HealthKitObserverEvent(BaseModel):
    """A HealthKit observer wake received by the mobile bridge."""

    eventType: Literal["healthkit_observer_triggered"]
    timestamp: datetime
    dataType: str


class BridgeHeartbeatEvent(BaseModel):
    """Durable bridge lifecycle and sync-attempt telemetry."""

    eventType: Literal["bridge_heartbeat"]
    timestamp: datetime
    trigger: str
    lastSyncRequestedAt: datetime | None = None
    lastSyncCompletedAt: datetime | None = None
    lastHealthKitEventAt: datetime | None = None
    lastError: str | None = None
    backgroundDeliveryStatus: dict[str, bool] = Field(default_factory=dict)


SDKLogEvent = Annotated[
    HistoricalDataSyncStartEvent
    | HistoricalDataTypeSyncEndEvent
    | DeviceStateEvent
    | BackgroundDeliveryRegistrationEvent
    | HealthKitObserverEvent
    | BridgeHeartbeatEvent,
    Field(discriminator="eventType"),
]


class SDKLogRequest(BaseModel):
    """Top-level request for SDK log events endpoint."""

    sdkVersion: str
    provider: str | None = None
    events: list[SDKLogEvent] = Field(..., min_length=1, max_length=100)
