"""Deterministic analytics over explicitly pinned immutable dataset versions."""
import calendar
from typing import Literal

from pydantic import Field

from mobility.contracts import Contract, DatasetReference, Dimension, Period
from mobility.storage import DatasetStore

Category = Literal['Member', 'Casual', 'Unknown', 'Classic', 'E-bike']
CATEGORIES = {'member_casual': ('Member', 'Casual', 'Unknown'), 'rideable_type': ('Classic', 'E-bike', 'Unknown')}


class CategoryMetric(Contract):
    category: Category
    count: int = Field(ge=0)
    share: float = Field(ge=0, le=100, allow_inf_nan=False)


class KpiSummary(Contract):
    dataset: DatasetReference
    total_trips: int = Field(gt=0)
    average_duration_minutes: float = Field(gt=0, allow_inf_nan=False)
    member_casual: tuple[CategoryMetric, ...]
    rideable_type: tuple[CategoryMetric, ...]


class DailyCount(Contract):
    day: int = Field(ge=1, le=31)
    count: int = Field(ge=0)


class DailyTrend(Contract):
    dataset: DatasetReference
    days: tuple[DailyCount, ...]


class StationChange(Contract):
    station_id: str
    station_name: str
    current_count: int = Field(ge=0)
    prior_count: int = Field(ge=0)
    delta: int
    percentage_change: float | None = Field(allow_inf_nan=False)
    eligible: bool
    eligibility_reason: str | None
    status: Literal['existing', 'new', 'removed', 'standalone']
    materiality: Literal['Flat', 'Moderate Change', 'Significant Change'] | None
    direction: Literal['increase', 'decrease', 'unchanged']


class StationRanking(Contract):
    dataset: DatasetReference
    stations: tuple[StationChange, ...]


class StationMovers(Contract):
    current_dataset: DatasetReference
    prior_dataset: DatasetReference
    top_5_increases: tuple[StationChange, ...]
    top_5_decreases: tuple[StationChange, ...]
    mandatory_investigation_candidate: StationChange | None


class MetricComparison(Contract):
    metric: Literal['total_trips', 'average_duration_minutes', 'share']
    dimension: Dimension | None = None
    category: Category | None = None
    current_value: int | float = Field(allow_inf_nan=False)
    prior_value: int | float = Field(allow_inf_nan=False)
    delta: int | float = Field(allow_inf_nan=False)
    unit: Literal['trips', 'minutes', 'percentage_points']
    percentage_change: float | None = Field(allow_inf_nan=False)
    eligible: bool
    eligibility_reason: str | None
    materiality: Literal['Flat', 'Moderate Change', 'Significant Change'] | None
    direction: Literal['increase', 'decrease', 'unchanged']


class PeriodComparison(Contract):
    current: KpiSummary
    prior: KpiSummary
    total_trips_change: int
    total_trips_percentage_change: float | None = Field(allow_inf_nan=False)
    average_duration_minutes_change: float = Field(allow_inf_nan=False)
    metrics: tuple[MetricComparison, ...]


class CategoryVariance(Contract):
    category: Category
    current_count: int = Field(ge=0)
    prior_count: int = Field(ge=0)
    delta: int
    eligible: bool
    eligibility_reason: str | None
    contribution_pct: float | None = Field(allow_inf_nan=False)


class ContributionLeader(Contract):
    category: Category
    contribution_pct: float = Field(allow_inf_nan=False)


class ContributionBreakdown(Contract):
    dimension: Dimension
    categories: tuple[CategoryVariance, ...]
    leaders: tuple[ContributionLeader, ...]
    wording: str | None


class StationVariance(Contract):
    current_dataset: DatasetReference
    prior_dataset: DatasetReference
    station: StationChange
    member_casual: ContributionBreakdown
    rideable_type: ContributionBreakdown


class DatasetInput(Contract):
    dataset: DatasetReference


class ComparisonInput(Contract):
    current_dataset: DatasetReference
    prior_dataset: DatasetReference


class StationInput(ComparisonInput):
    station_id: str = Field(min_length=1)


class RankingInput(DatasetInput):
    top_n: int = Field(default=5, ge=1, le=100)


def prior_period(period: Period) -> Period:
    if period.month == 1:
        if period.year == 1:
            raise ValueError('No supported prior period')
        return Period(year=period.year - 1, month=12)
    return Period(year=period.year, month=period.month - 1)


def require_adjacent(current: DatasetReference, prior: DatasetReference) -> None:
    if prior_period(current.period) != prior.period:
        raise ValueError('Comparison requires adjacent calendar months')


def station_change(station_id: str, name: str, current: int, prior: int) -> StationChange:
    status = 'new' if prior == 0 else 'removed' if current == 0 else 'existing'
    reason = status if status != 'existing' else 'prior_sample_below_100' if prior < 100 else None
    delta = current - prior
    pct = delta / prior * 100 if reason is None else None
    materiality = None if pct is None else 'Flat' if abs(pct) < 5 else 'Moderate Change' if abs(pct) <= 10 else 'Significant Change'
    return StationChange(station_id=station_id, station_name=name, current_count=current, prior_count=prior,
        delta=delta, percentage_change=pct, eligible=reason is None, eligibility_reason=reason,
        status=status, materiality=materiality, direction='increase' if delta > 0 else 'decrease' if delta < 0 else 'unchanged')


def _wording(leaders: tuple[ContributionLeader, ...]) -> str | None:
    if not leaders:
        return None
    value = leaders[0].contribution_pct
    if len(leaders) > 1:
        labels = ', '.join('Unknown (unclassified)' if item.category == 'Unknown' else item.category for item in leaders)
        rendered = f'{value:.2f}'.rstrip('0').rstrip('.')
        return f'Jointly led by {labels} (each {rendered}%).'
    label = leaders[0].category
    if label == 'Unknown':
        return 'Driven primarily by unclassified data.'
    if value > 100:
        return f'More than accounted for by {label}.'
    if value == 100:
        return f'Driven entirely by {label}.'
    if value >= 80:
        return f'Primarily driven by {label}.'
    return 'Driven by a mix of factors.'


def contribution_breakdown(current: dict[str, int], prior: dict[str, int], delta: int, dimension: Dimension) -> ContributionBreakdown:
    categories = tuple(CategoryVariance(category=category, current_count=int(current.get(category, 0)),
        prior_count=int(prior.get(category, 0)), delta=int(current.get(category, 0)) - int(prior.get(category, 0)),
        eligible=delta != 0 and prior.get(category, 0) >= 100,
        eligibility_reason='zero_total_change' if delta == 0 else 'prior_sample_below_100' if prior.get(category, 0) < 100 else None,
        contribution_pct=(int(current.get(category, 0)) - int(prior.get(category, 0))) / delta * 100
            if delta != 0 and prior.get(category, 0) >= 100 else None) for category in CATEGORIES[dimension])
    eligible = tuple(item for item in categories if item.eligible)
    maximum = max((item.contribution_pct for item in eligible), default=None)
    leaders = tuple(ContributionLeader(category=item.category, contribution_pct=item.contribution_pct)
                    for item in eligible if item.contribution_pct == maximum)
    return ContributionBreakdown(dimension=dimension, categories=categories, leaders=leaders, wording=_wording(leaders))


class AnalyticsService:
    def __init__(self, store: DatasetStore) -> None:
        self.store = store

    def kpi_summary(self, reference: DatasetReference) -> KpiSummary:
        reference = DatasetInput(dataset=reference).dataset
        metrics = self.store.read_kpis(reference)
        return KpiSummary(dataset=reference, total_trips=metrics['total_trips'],
            average_duration_minutes=metrics['average_duration_minutes'],
            **{dimension: tuple(CategoryMetric(category=category, count=values['count'], share=float(values['share']))
                for category, values in metrics['categories'][dimension].items()) for dimension in CATEGORIES})

    def compare_periods(self, current: DatasetReference, prior: DatasetReference) -> PeriodComparison:
        args = ComparisonInput(current_dataset=current, prior_dataset=prior)
        require_adjacent(args.current_dataset, args.prior_dataset)
        now, before = self.kpi_summary(current), self.kpi_summary(prior)
        delta = now.total_trips - before.total_trips
        metrics = self._comparison_metrics(now, before)
        return PeriodComparison(current=now, prior=before, total_trips_change=delta,
            total_trips_percentage_change=metrics[0].percentage_change,
            average_duration_minutes_change=now.average_duration_minutes - before.average_duration_minutes,
            metrics=metrics)

    @staticmethod
    def _comparison_metrics(now: KpiSummary, before: KpiSummary) -> tuple[MetricComparison, ...]:
        values = [('total_trips', None, None, now.total_trips, before.total_trips, 'trips', before.total_trips),
                  ('average_duration_minutes', None, None, now.average_duration_minutes,
                   before.average_duration_minutes, 'minutes', before.total_trips)]
        for dimension in CATEGORIES:
            old = {item.category: item for item in getattr(before, dimension)}
            values.extend(('share', dimension, item.category, item.share, old[item.category].share,
                           'percentage_points', old[item.category].count) for item in getattr(now, dimension))
        results = []
        for metric, dimension, category, current_value, prior_value, unit, prior_count in values:
            eligible = metric == 'total_trips' and prior_count >= 100 and prior_value != 0
            pct = (current_value - prior_value) / prior_value * 100 if eligible else None
            results.append(MetricComparison(metric=metric, dimension=dimension, category=category,
                current_value=current_value, prior_value=prior_value, delta=current_value - prior_value,
                unit=unit, percentage_change=pct, eligible=eligible,
                eligibility_reason=None if eligible else 'percentage_not_applicable' if metric != 'total_trips' else 'zero_prior_value' if prior_value == 0 else 'prior_sample_below_100',
                materiality=None if pct is None else 'Flat' if abs(pct) < 5 else 'Moderate Change' if abs(pct) <= 10 else 'Significant Change',
                direction='increase' if current_value > prior_value else 'decrease' if current_value < prior_value else 'unchanged'))
        return tuple(results)

    def daily_trend(self, reference: DatasetReference) -> DailyTrend:
        reference = DatasetInput(dataset=reference).dataset
        frame = self.store.read_frame(reference)
        counts = self.store._dates(frame['started_at']).dt.day.value_counts()
        return DailyTrend(dataset=reference, days=tuple(DailyCount(day=day, count=int(counts.get(day, 0)))
            for day in range(1, calendar.monthrange(reference.period.year, reference.period.month)[1] + 1)))

    @staticmethod
    def _stations(frame):
        counts = {str(key): int(value) for key, value in frame.groupby('start_station_id').size().items()}
        names = {}
        if 'start_station_name' in frame:
            for station, name in zip(frame['start_station_id'], frame['start_station_name']):
                if str(name).strip():
                    names.setdefault(str(station), str(name))
        return counts, names

    def station_analysis(self, reference: DatasetReference, top_n: int = 5) -> StationRanking:
        args = RankingInput(dataset=reference, top_n=top_n)
        counts, names = self._stations(self.store.read_frame(args.dataset))
        stations = tuple(station_change(key, names.get(key, key), count, 0).model_copy(update={
            'status': 'standalone', 'eligibility_reason': 'comparison_unavailable'})
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:args.top_n])
        return StationRanking(dataset=reference, stations=stations)

    def station_movers(self, current: DatasetReference, prior: DatasetReference) -> StationMovers:
        args = ComparisonInput(current_dataset=current, prior_dataset=prior)
        require_adjacent(args.current_dataset, args.prior_dataset)
        now, names = self._stations(self.store.read_frame(current))
        before, old_names = self._stations(self.store.read_frame(prior))
        changes = tuple(station_change(key, names.get(key, old_names.get(key, key)), now.get(key, 0), before.get(key, 0))
                        for key in sorted(now.keys() | before.keys()))
        increases = tuple(sorted((s for s in changes if s.delta > 0), key=lambda s: (-s.delta, s.station_id)))
        decreases = tuple(sorted((s for s in changes if s.delta < 0), key=lambda s: (s.delta, s.station_id)))
        candidate = next((s for s in decreases if s.eligible and s.percentage_change < -10 and s.delta < -100), None)
        return StationMovers(current_dataset=current, prior_dataset=prior, top_5_increases=increases[:5],
            top_5_decreases=decreases[:5], mandatory_investigation_candidate=candidate)

    def analyze_station_variance(self, station_id: str, current: DatasetReference, prior: DatasetReference) -> StationVariance:
        args = StationInput(station_id=station_id, current_dataset=current, prior_dataset=prior)
        require_adjacent(args.current_dataset, args.prior_dataset)
        now_frame = self.store.read_frame(current)
        prior_frame = self.store.read_frame(prior)
        now = now_frame[now_frame['start_station_id'] == station_id]
        before = prior_frame[prior_frame['start_station_id'] == station_id]
        if now.empty and before.empty:
            raise ValueError('Station is absent from both pinned datasets')
        _, names = self._stations(now if not now.empty else before)
        station = station_change(station_id, names.get(station_id, station_id), len(now), len(before))
        return StationVariance(current_dataset=current, prior_dataset=prior, station=station,
            **{dimension: contribution_breakdown(now[dimension].value_counts().to_dict(),
                before[dimension].value_counts().to_dict(), station.delta, dimension) for dimension in CATEGORIES})
