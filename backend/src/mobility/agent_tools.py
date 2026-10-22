"""Bounded agent tool dispatch over immutable, already pinned dataset references."""
from typing import Any

from mobility.analytics import AnalyticsService
from mobility.contracts import DatasetReference, EvidenceValue, Period, ToolArguments, ToolResult
from mobility.storage import DatasetStore


_FIELDS = {
    'get_available_periods': frozenset(),
    'retrieve_context': frozenset(),
    'kpi_summary': frozenset({'current_period'}),
    'compare_periods': frozenset({'current_period', 'comparison_period'}),
    'station_analysis': frozenset({'current_period', 'top_n'}),
    'station_movers': frozenset({'current_period', 'comparison_period'}),
    'analyze_station_variance': frozenset({'current_period', 'comparison_period', 'station_id'}),
}
_CONTEXT = {
    'scope': 'Supported: monthly trips, rider/fleet shares, average duration, station starts and adjacent-month comparisons. Forecasts, causal claims and non-adjacent comparisons are unsupported.',
    'definitions': 'A trip is a cleaned start in the reporting month. Shares include Unknown (unclassified). Station volume is starts. Percent changes require at least 100 prior starts.',
    'templates': 'Claims must use exact tool evidence. Python renders validated values and fixed transitions; do not generate factual prose.',
}


class AgentTools:
    def __init__(self, store: DatasetStore, refs: tuple[DatasetReference, ...], run_id: str) -> None:
        if not refs or len(refs) > 2 or len({ref.period for ref in refs}) != len(refs):
            raise ValueError('One or two unique pinned datasets are required')
        self.store = store
        self.refs = tuple(DatasetReference.model_validate(ref) for ref in refs)
        self.run_id = run_id
        self.analytics = AnalyticsService(store)
        self.by_period = {ref.period: ref for ref in self.refs}

    def _reference(self, period: Period | None) -> DatasetReference:
        if period is None or period not in self.by_period:
            raise ValueError('Requested period is not in the pinned datasets')
        return self.by_period[period]

    @staticmethod
    def _value(ref: DatasetReference, entity: str, metric: str, exact: int | float | None,
               unit: str = 'trips', *, comparison: Period | None = None, dimension: str | None = None,
               category: str | None = None, reason: str | None = None) -> EvidenceValue:
        return EvidenceValue(entity_id=entity, metric_type=metric, period=ref.period,
            comparison_period=comparison, dimension=dimension, category=category, unit=unit,
            exact_tool_value=exact, eligible=exact is not None, eligibility_reason=reason)

    def _summary_values(self, summary) -> list[EvidenceValue]:
        ref = summary.dataset
        values = [self._value(ref, 'month', 'trip_count', summary.total_trips),
                  self._value(ref, 'month', 'average_duration_minutes', summary.average_duration_minutes, 'minutes')]
        for dimension in ('member_casual', 'rideable_type'):
            for item in getattr(summary, dimension):
                values.append(self._value(ref, item.category, 'trip_count', item.count, dimension=dimension, category=item.category))
                values.append(self._value(ref, item.category, 'share', item.share, 'percent', dimension=dimension, category=item.category))
        return values

    def _station_values(self, ref, station, comparison=None):
        values = [self._value(ref, station.station_id, 'current_volume', station.current_count, comparison=comparison)]
        if comparison is not None:
            values.extend((self._value(self._reference(comparison), station.station_id, 'current_volume', station.prior_count),
                           self._value(ref, station.station_id, 'absolute_change', station.delta, comparison=comparison),
                           self._value(ref, station.station_id, 'percentage_change', station.percentage_change,
                               'percent', comparison=comparison, reason=station.eligibility_reason)))
        return values

    def execute(self, name: str, args: ToolArguments, call_id: str) -> tuple[ToolResult, dict[str, Any]]:
        args = ToolArguments.model_validate(args)
        datasets = (self.refs[0],)
        try:
            if name not in _FIELDS:
                raise ValueError('Tool is outside the approved Phase 4 whitelist')
            supplied = {key for key, value in args.model_dump().items() if value is not None}
            allowed = _FIELDS[name]
            required = allowed - {'top_n'}
            if not required <= supplied or not supplied <= allowed:
                raise ValueError('Tool arguments do not match the approved schema')
            if name == 'get_available_periods':
                payload = {'periods': [ref.period.model_dump() for ref in self.refs],
                           'datasets': [ref.model_dump() for ref in self.refs]}
                values = []
            elif name == 'retrieve_context':
                payload, values = dict(_CONTEXT), []
            else:
                current = self._reference(args.current_period)
                datasets = (current,)
                prior = None
                if args.comparison_period is not None:
                    prior = self._reference(args.comparison_period)
                    datasets = (current, prior)
                if name == 'kpi_summary':
                    result = self.analytics.kpi_summary(current)
                    values = self._summary_values(result)
                elif name == 'compare_periods':
                    result = self.analytics.compare_periods(current, prior)
                    values = self._summary_values(result.current) + self._summary_values(result.prior)
                    for metric in result.metrics:
                        entity = metric.category or metric.metric
                        values.append(self._value(current, entity, 'absolute_change', metric.delta, metric.unit,
                            comparison=prior.period, dimension=metric.dimension, category=metric.category))
                        values.append(self._value(current, entity, 'percentage_change', metric.percentage_change,
                            'percent', comparison=prior.period, dimension=metric.dimension,
                            category=metric.category, reason=metric.eligibility_reason))
                elif name == 'station_analysis':
                    result = self.analytics.station_analysis(current, args.top_n or 5)
                    values = [value for station in result.stations for value in self._station_values(current, station)]
                elif name == 'station_movers':
                    result = self.analytics.station_movers(current, prior)
                    stations = {station.station_id: station for station in (*result.top_5_increases, *result.top_5_decreases)}
                    if result.mandatory_investigation_candidate is not None:
                        station = result.mandatory_investigation_candidate
                        stations[station.station_id] = station
                    values = [value for station in stations.values() for value in self._station_values(current, station, prior.period)]
                else:
                    result = self.analytics.analyze_station_variance(args.station_id, current, prior)
                    values = self._station_values(current, result.station, prior.period)
                    for dimension in ('member_casual', 'rideable_type'):
                        for category in getattr(result, dimension).categories:
                            values.extend((self._value(current, result.station.station_id, 'current_volume',
                                category.current_count, dimension=dimension, category=category.category),
                                self._value(prior, result.station.station_id, 'current_volume',
                                category.prior_count, dimension=dimension, category=category.category),
                                self._value(current, result.station.station_id, 'absolute_change',
                                category.delta, comparison=prior.period, dimension=dimension,
                                category=category.category)))
                            values.append(self._value(current, result.station.station_id, 'contribution',
                                category.contribution_pct, 'percent', comparison=prior.period,
                                dimension=dimension, category=category.category, reason=category.eligibility_reason))
                payload = result.model_dump(mode='json')
            tool_result = ToolResult(run_id=self.run_id, tool_call_id=call_id, stage='execution',
                tool_name=name, status='success', arguments=args, datasets=datasets, values=tuple(values))
            return tool_result, payload
        except (ValueError, TypeError, KeyError, OSError) as exc:
            reason = 'Tool arguments or pinned data are invalid.' if isinstance(exc, (ValueError, TypeError, KeyError)) else 'Tool execution failed.'
            return ToolResult(run_id=self.run_id, tool_call_id=call_id, stage='execution',
                tool_name=name if name in ToolResult.model_fields['tool_name'].annotation.__args__ else 'retrieve_context',
                status='failed', arguments=args, datasets=datasets, values=(), validation_reason=reason), {}
