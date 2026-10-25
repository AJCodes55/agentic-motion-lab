"""Typed ad-hoc queries over pinned analytics; no generated code or factual prose."""
from html import escape
import os
from typing import Literal

from pydantic import Field, model_validator

from mobility.agent_tools import AgentTools
from mobility.analytics import prior_period
from mobility.baseline import BaselineReport, generate_standard_dashboard, _table, _report_document, _chart_region
from mobility.contracts import Contract, DatasetReference, Period, ToolArguments, ToolResult
from mobility.storage import DatasetStore


class AdhocRequest(Contract):
    period: Period
    metric: Literal['total_trips', 'member_share', 'fleet_share', 'average_duration', 'station_starts']
    comparison: bool = False
    comparison_period: Period | None = None
    station_query: str | None = Field(default=None, min_length=1, max_length=500)
    station_id: str | None = Field(default=None, min_length=1)
    chart: bool = False

    @model_validator(mode='after')
    def scoped_arguments(self):
        if self.station_query is not None and not self.station_query.strip():
            raise ValueError('Station query cannot be blank')
        if self.metric != 'station_starts' and (self.station_query is not None or self.station_id is not None):
            raise ValueError('Station arguments require a station metric')
        if self.comparison_period is not None and not self.comparison:
            raise ValueError('A comparison period requires comparison')
        return self


class StationChoice(Contract):
    station_id: str
    station_name: str


class AdhocResult(Contract):
    status: Literal['success', 'needs_station_selection', 'refused']
    message: str
    period: Period
    report_id: str | None = None
    datasets: tuple[DatasetReference, ...] = ()
    station_choices: tuple[StationChoice, ...] = ()
    html: str = ''
    evidence: tuple[ToolResult, ...] = ()
    chart_svg: str | None = None
    error_code: Literal['ERR_UNSUPPORTED_INTENT'] | None = None


def _display(value):
    return 'N/A' if value is None else f'{value:.2f}'.rstrip('0').rstrip('.') if isinstance(value, float) else str(value)


def make_chart(title: str, source: ToolResult, run_id: str) -> str:
    """Render only verified scalar evidence with escaped labels and fixed SVG markup."""
    source = ToolResult.model_validate(source)
    periods = {ref.period for ref in source.datasets}
    if source.status != 'success' or source.run_id != run_id or not periods:
        raise ValueError('Chart requires successful evidence from this run')
    if any(value.period not in periods or (value.comparison_period is not None and value.comparison_period not in periods) for value in source.values):
        raise ValueError('Chart evidence periods must match pinned datasets')
    plotted = tuple(value for value in source.values if value.exact_tool_value is not None)
    maximum = max((abs(value.exact_tool_value) for value in plotted), default=1) or 1
    rows = []
    for index, value in enumerate(plotted):
        label = f'{value.period.year:04d}-{value.period.month:02d} {value.category or value.entity_id} {value.metric_type}'
        label = label.replace('Unknown', 'Unknown (unclassified)')
        number = value.exact_tool_value
        y = 40 + 40 * index
        width = abs(number) / maximum * 220
        x = 490 - width if number < 0 else 490
        rows.append(f'<text x="5" y="{y}">{escape(label)}</text><rect x="{x:.3f}" y="{y-15}" width="{width:.3f}" height="20" fill="#155e75"/><text x="720" y="{y}">{escape(_display(number))} {escape(value.unit)}</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{escape(title, quote=True)}" viewBox="0 0 930 {max(100, 60+40*len(plotted))}"><title>{escape(title)}</title>{"".join(rows)}</svg>'


class AdhocService:
    def __init__(self, store: DatasetStore) -> None:
        self.store = store

    def _refusal(self, request, message):
        return AdhocResult(status='refused', period=request.period,
            message=message + ' Try a supported single-month metric or station starts query.',
            error_code='ERR_UNSUPPORTED_INTENT')

    def _choices(self, refs, request):
        stations: dict[str, set[str]] = {}
        for ref in refs:
            frame = self.store.read_frame(ref)
            for station_id, name in zip(frame['start_station_id'], frame['start_station_name']):
                stations.setdefault(str(station_id), set()).add(str(name))
        if request.station_id is not None:
            ids = [request.station_id] if request.station_id in stations else []
        else:
            query = (request.station_query or '').strip().casefold()
            exact = [key for key, names in stations.items() if query == key.casefold() or any(query == name.casefold() for name in names)]
            ids = exact or [key for key, names in stations.items() if query in key.casefold() or any(query in name.casefold() for name in names)]
        return tuple(StationChoice(station_id=key, station_name=sorted(stations[key])[0]) for key in sorted(ids))

    def run(self, request: AdhocRequest, baseline: BaselineReport | None = None) -> AdhocResult:
        request = AdhocRequest.model_validate(request)
        if baseline is not None and baseline.period != request.period:
            raise ValueError('Baseline reporting month does not match request')
        available = {item.period for item in baseline.datasets} if baseline is not None else {item.period for item in self.store.list_active()}
        if request.period not in available:
            return self._refusal(request, 'The requested reporting month is unavailable.')
        if request.comparison and request.metric != 'station_starts':
            return self._refusal(request, 'The four monthly metrics support single-month queries only.')
        previous = None
        if request.comparison:
            try:
                previous = prior_period(request.period)
            except ValueError:
                return self._refusal(request, 'The immediately preceding month is unavailable.')
            if request.comparison_period is not None and request.comparison_period != previous:
                return self._refusal(request, 'Only the immediately preceding calendar month can be compared.')
            if previous not in available:
                return self._refusal(request, 'The immediately preceding month is unavailable; this comparison cannot run.')
        baseline = baseline or generate_standard_dashboard(self.store, request.period)
        refs = tuple(ref for ref in baseline.datasets if ref.period in (request.period, previous))
        if previous is not None and previous not in {ref.period for ref in refs}:
            return self._refusal(request, 'The preceding month is unavailable in this reporting snapshot.')
        if request.metric == 'station_starts':
            choices = self._choices(refs, request)
            if (request.station_id is None and request.station_query is None) or len(choices) > 1:
                return AdhocResult(status='needs_station_selection', period=request.period,
                    message='Select an explicit station and submit the reporting month again.', station_choices=choices)
            if not choices:
                return self._refusal(request, 'No matching start station exists in the requested months.')
        # Every selected calculation uses the baseline's immutable snapshot, even after replacement.
        refs = baseline.datasets if request.comparison else (baseline.datasets[0],)
        tools = AgentTools(self.store, refs, baseline.report_id)
        available_result, _ = tools.execute('get_available_periods', ToolArguments(), 'adhoc_available')
        result, title = self._calculate(request, refs, tools)
        if result is None:
            return self._refusal(request, title)
        if result.status != 'success':
            return self._refusal(request, 'The requested calculation could not be verified.')
        values = result.values
        chart = make_chart(title, result, baseline.report_id) if request.chart else None
        evidence = (available_result, result)
        if chart:
            evidence += (result.model_copy(update={'tool_name': 'make_chart', 'tool_call_id': 'adhoc_chart', 'stage': 'rendering'}),)
        rows = ((f'{v.period.year:04d}-{v.period.month:02d}', (v.category or v.entity_id).replace('Unknown', 'Unknown (unclassified)'), v.metric_type, _display(v.exact_tool_value), v.unit, v.eligibility_reason or '') for v in values)
        body = _table(('Month', 'Entity / category', 'Metric', 'Value', 'Unit', 'Eligibility reason'), rows)
        if chart:
            body += '<p class="report-note">Exact values are provided in the table. Scroll the chart horizontally on narrow screens.</p>' + _chart_region(chart)
        html = _report_document(title, body)
        output = AdhocResult(status='success', message=title, period=request.period,
            report_id=baseline.report_id, datasets=refs, html=html, evidence=evidence, chart_svg=chart)
        self._persist(output)
        return output

    def _calculate(self, request, refs, tools):
        args = ToolArguments(current_period=refs[0].period, comparison_period=refs[1].period if request.comparison else None)
        if request.metric == 'station_starts':
            choices = self._choices(refs, request)
            if len(choices) != 1:
                return None, 'Station selection no longer resolves uniquely in the pinned snapshot.'
            station = choices[0]
            if request.comparison:
                args = args.model_copy(update={'station_id': station.station_id})
                result, _ = tools.execute('analyze_station_variance', args, 'adhoc_query')
            else:
                frame = self.store.read_frame(refs[0])
                count = int((frame['start_station_id'] == station.station_id).sum())
                value = AgentTools._value(refs[0], station.station_id, 'current_volume', count)
                result = ToolResult(run_id=tools.run_id, tool_call_id='adhoc_query', stage='execution', tool_name='station_analysis', status='success', arguments=args.model_copy(update={'station_id': station.station_id}), datasets=refs, values=(value,))
            return result, f'Station starts: {station.station_name} ({station.station_id})'
        tool = 'compare_periods' if request.comparison else 'kpi_summary'
        result, _ = tools.execute(tool, args, 'adhoc_query')
        dimension = {'member_share': 'member_casual', 'fleet_share': 'rideable_type'}.get(request.metric)
        metric = {'total_trips': 'trip_count', 'average_duration': 'average_duration_minutes'}.get(request.metric, 'share')
        values = tuple(value for value in result.values if
            (value.metric_type == metric and value.dimension == dimension) or
            (request.comparison and value.metric_type == 'absolute_change' and value.dimension == dimension and
             (dimension is not None or value.entity_id == ('total_trips' if request.metric == 'total_trips' else 'average_duration_minutes'))))
        return result.model_copy(update={'values': values}), request.metric.replace('_', ' ').capitalize()

    def _persist(self, result):
        root = self.store.root / 'reports' / result.report_id
        # Artifacts are created once; report IDs are generated by the archived baseline.
        files = {'adhoc.html': result.html}
        if result.chart_svg:
            files['adhoc-chart.svg'] = result.chart_svg
        # Publish the metadata manifest last; history cannot expose a partial ad-hoc report.
        files['adhoc.json'] = result.model_dump_json(indent=2)
        staged = []
        published = []
        try:
            for name, content in files.items():
                temporary = root / ('.' + name + '.tmp')
                staged.append(temporary)
                with temporary.open('x', encoding='utf-8') as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
            for temporary in staged:
                destination = root / temporary.name[1:-4]
                if destination.exists():
                    raise FileExistsError('Ad-hoc archive already exists')
                temporary.rename(destination)
                published.append(destination)
            self.store._sync_directory(root)
        except BaseException:
            for destination in published:
                destination.unlink(missing_ok=True)
            raise
        finally:
            for temporary in staged:
                temporary.unlink(missing_ok=True)
