"""Immutable contracts; later phases implement their behavior."""
from typing import Annotated, Generic, Literal, Self, TypeVar
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class Period(Contract):
    year: int = Field(ge=1, le=9999)
    month: int = Field(ge=1, le=12)


class DatasetReference(Contract):
    period: Period
    version_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class AnalysisRequest(Contract):
    period: Period
    command: str = Field(min_length=1, max_length=2000)
    station_id: str | None = Field(default=None, min_length=1, max_length=128)


class QualitySummary(Contract):
    source_filenames: tuple[str, ...] = ()
    per_csv_parsed_counts: tuple[Annotated[int, Field(ge=0)], ...] = ()
    invalid_timestamp_rows: int = Field(default=0, ge=0)
    outside_month_rows: int = Field(default=0, ge=0)
    duplicate_rows: int = Field(default=0, ge=0)
    missing_station_rows: int = Field(default=0, ge=0)
    invalid_duration_rows: int = Field(default=0, ge=0)
    unknown_member_rows: int = Field(default=0, ge=0)
    unknown_bike_rows: int = Field(default=0, ge=0)
    month_threshold_denominator: int = Field(default=0, ge=0)
    station_threshold_denominator: int = Field(default=0, ge=0)
    rejection_reason: str | None = Field(default=None, max_length=256)
    source_rows: int = Field(ge=0)
    valid_rows: int = Field(ge=0)
    excluded_rows: int = Field(ge=0)

    @model_validator(mode='after')
    def reconcile(self) -> Self:
        if self.source_rows != self.valid_rows + self.excluded_rows:
            raise ValueError('Quality row counts must reconcile')
        if len(self.source_filenames) != len(self.per_csv_parsed_counts):
            raise ValueError('Each source file requires a parsed count')
        if self.per_csv_parsed_counts and sum(self.per_csv_parsed_counts) != self.source_rows:
            raise ValueError('Per-file counts must reconcile')
        if self.source_rows > 0 and self.valid_rows == 0 and self.rejection_reason is None:
            raise ValueError('Empty cleaned data requires a rejection reason')
        return self


Metric = Literal['trip_count', 'share', 'average_duration_minutes', 'absolute_change', 'percentage_change', 'contribution', 'current_volume']
Dimension = Literal['rideable_type', 'member_casual']
ExactValue = int | float | None


class EvidenceValue(Contract):
    entity_id: str = Field(min_length=1, max_length=128)
    metric_type: Metric
    period: Period
    comparison_period: Period | None = None
    dimension: Dimension | None = None
    category: Literal['Member', 'Casual', 'Classic', 'E-bike', 'Unknown'] | None = None
    unit: Literal['trips', 'percent', 'minutes', 'percentage_points']
    exact_tool_value: ExactValue = Field(allow_inf_nan=False)
    eligible: bool
    eligibility_reason: str | None = Field(default=None, max_length=256)

    @model_validator(mode='after')
    def validate_eligibility(self) -> Self:
        if not self.eligible and self.exact_tool_value is not None:
            raise ValueError('Ineligible values must be null')
        if self.eligible and self.exact_tool_value is None:
            raise ValueError('Eligible values require a value')
        return self


class ToolArguments(Contract):
    current_period: Period | None = None
    comparison_period: Period | None = None
    station_id: str | None = Field(default=None, max_length=128)
    top_n: int | None = Field(default=None, ge=1, le=100)
    dimension: Dimension | None = None


class ToolResult(Contract):
    run_id: str = Field(min_length=1, max_length=128)
    tool_call_id: str = Field(min_length=1, max_length=128)
    stage: Literal['baseline', 'routing', 'planning', 'execution', 'validation', 'rendering']
    tool_name: Literal['kpi_summary', 'compare_periods', 'daily_trend', 'station_analysis', 'station_movers', 'analyze_station_variance', 'make_chart', 'get_available_periods', 'retrieve_context', 'generate_standard_dashboard', 'validate_and_load_file']
    status: Literal['success', 'failed']
    arguments: ToolArguments
    datasets: tuple[DatasetReference, ...] = Field(min_length=1, max_length=2)
    values: tuple[EvidenceValue, ...]
    validation_reason: str | None = Field(default=None, max_length=256)


class Claim(EvidenceValue):
    claim_id: str = Field(min_length=1, max_length=128)
    tool_call_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    datasets: tuple[DatasetReference, ...] = Field(min_length=1, max_length=2)
    transition: Literal['increase', 'decrease', 'unchanged', 'standalone']


class ApiError(Contract):
    code: Literal['HTTP_ERROR', 'VALIDATION_ERROR', 'INTERNAL_ERROR', 'ERR_SCHEMA_MISMATCH', 'ERR_UNSUPPORTED_INTENT', 'ERR_TOOL_EXECUTION', 'ERR_UNGROUNDED_CLAIM', 'ERR_BUDGET_EXCEEDED']
    message: str
    request_id: str
    run_id: str | None = None
    stage: Literal['baseline', 'routing', 'planning', 'execution', 'validation', 'rendering'] | None = None
    validation_reason: str | None = Field(default=None, max_length=256)


T = TypeVar('T')


class ApiResponse(Contract, Generic[T]):
    success: bool
    data: T | None
    error: ApiError | None

    @model_validator(mode='after')
    def validate_outcome(self) -> Self:
        if self.success != (self.error is None) or (not self.success and self.data is not None):
            raise ValueError('Response outcome is inconsistent')
        return self


class HealthData(Contract):
    status: Literal['ok']
    service: Literal['citibike-analytics']
