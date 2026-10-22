"""Immutable contracts; later phases implement their behavior."""
from typing import Annotated, Generic, Literal, Self, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    station_id: str | None = Field(default=None, min_length=1)


class CategoryMapping(Contract):
    raw_value: str
    normalized_value: Literal['Member', 'Casual', 'Classic', 'E-bike', 'Unknown']
    count: int = Field(ge=0)


class QualitySummary(Contract):
    status: Literal['accepted', 'rejected'] = 'accepted'
    stopped_stage: Literal['validation', 'timestamps', 'month', 'deduplication', 'stations', 'duration', 'categories', 'reconciliation', 'storage'] | None = None
    candidate_rows: int = Field(default=0, ge=0)
    member_value_mappings: tuple[CategoryMapping, ...] = ()
    bike_value_mappings: tuple[CategoryMapping, ...] = ()
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
        if self.source_rows != self.valid_rows + self.excluded_rows + self.candidate_rows:
            raise ValueError('Quality row counts must reconcile')
        if self.status == 'accepted' and self.candidate_rows != 0:
            raise ValueError('Accepted data cannot contain unprocessed candidate rows')
        if self.status == 'rejected' and (self.valid_rows != 0 or not self.rejection_reason):
            raise ValueError('Rejected data requires a reason and zero accepted rows')
        if len(self.source_filenames) != len(self.per_csv_parsed_counts):
            raise ValueError('Each source file requires a parsed count')
        if self.per_csv_parsed_counts and sum(self.per_csv_parsed_counts) != self.source_rows:
            raise ValueError('Per-file counts must reconcile')
        if self.source_rows > 0 and self.valid_rows == 0 and self.rejection_reason is None:
            raise ValueError('Empty cleaned data requires a rejection reason')
        return self


class PublicQualitySummary(QualitySummary):
    """Bounded UI summary; full source dictionaries remain in version metadata."""
    member_value_mappings: tuple[CategoryMapping, ...] = Field(default=(), exclude=True)
    bike_value_mappings: tuple[CategoryMapping, ...] = Field(default=(), exclude=True)
    source_filenames: tuple[Annotated[str, Field(max_length=256)], ...] = Field(default=(), max_length=100)
    source_labels_truncated: bool = False

    @classmethod
    def from_summary(cls, quality: QualitySummary) -> Self:
        values = quality.model_dump(exclude={'member_value_mappings', 'bike_value_mappings'})
        values['source_labels_truncated'] = any(len(name) > 256 for name in quality.source_filenames)
        values['source_filenames'] = tuple(name if len(name) <= 256 else '…' + name[-255:] for name in quality.source_filenames)
        return cls(**values)


Metric = Literal['trip_count', 'share', 'average_duration_minutes', 'absolute_change', 'percentage_change', 'contribution', 'current_volume']
Dimension = Literal['rideable_type', 'member_casual']
ExactValue = int | float | None


class EvidenceValue(Contract):
    entity_id: str = Field(min_length=1)
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
    station_id: str | None = Field(default=None, min_length=1)
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
    code: Literal['HTTP_ERROR', 'VALIDATION_ERROR', 'INTERNAL_ERROR', 'ERR_SCHEMA_MISMATCH', 'ERR_UNSUPPORTED_INTENT', 'ERR_TOOL_EXECUTION', 'ERR_UNGROUNDED_CLAIM', 'ERR_BUDGET_EXCEEDED', 'ERR_UPLOAD_LIMIT', 'ERR_INGESTION_BUSY', 'ERR_SOURCE_UNAVAILABLE', 'ERR_UPLOAD_TIMEOUT']
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


class FetchRequest(Contract):
    period: Period


class MonthIngestionResult(Contract):
    period: Period | None
    status: Literal['accepted', 'rejected']
    dataset: DatasetReference | None
    quality: PublicQualitySummary
    message: str = Field(max_length=256)
    error_code: str | None = Field(default=None, max_length=64)

    @field_validator('quality', mode='before')
    @classmethod
    def public_summary(cls, value: object) -> object:
        if isinstance(value, QualitySummary):
            return PublicQualitySummary.from_summary(value)
        return value

    @model_validator(mode='after')
    def validate_result(self) -> Self:
        if self.status != self.quality.status:
            raise ValueError('Result and quality status must agree')
        if self.status == 'accepted':
            if self.dataset is None or self.dataset.period != self.period or self.error_code is not None:
                raise ValueError('Accepted data requires the matching activated dataset')
        elif self.dataset is not None:
            raise ValueError('Rejected data cannot activate a dataset')
        return self


class IngestionBatch(Contract):
    ingestion_id: str = Field(min_length=1, max_length=128)
    results: tuple[MonthIngestionResult, ...] = Field(min_length=1, max_length=2)


class AvailablePeriods(Contract):
    periods: tuple[DatasetReference, ...]
