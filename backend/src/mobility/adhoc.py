"""Typed ad-hoc queries over pinned analytics; no generated code or factual prose."""
from html import escape
import os
from typing import Literal

from pydantic import Field, model_validator

from mobility.agent_tools import AgentTools
from mobility.analytics import CATEGORIES, prior_period
from mobility.baseline import BaselineReport, generate_standard_dashboard, _table, _report_document, _chart_region
from mobility.contracts import Contract, DatasetReference, Period, ToolArguments, ToolResult
from mobility.report_layout import dashboard, kpi_card, panel, segment_panel
from mobility.storage import DatasetStore
from mobility.tracing import TraceRecorder


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
        subject = (f'#{value.ranking.rank} {value.ranking.station_name}' if value.ranking is not None
                   else value.category or value.entity_id)
        label = f'{value.period.year:04d}-{value.period.month:02d} {subject} {value.metric_type}'
        label = label.replace('Unknown', 'Unknown (unclassified)')
        number = value.exact_tool_value
        y = 40 + 40 * index
        width = abs(number) / maximum * 220
        x = 490 - width if number < 0 else 490
        rows.append(f'<text x="5" y="{y}">{escape(label)}</text><rect x="{x:.3f}" y="{y-15}" width="{width:.3f}" height="20" fill="#155e75"/><text x="720" y="{y}">{escape(_display(number))} {escape(value.unit)}</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{escape(title, quote=True)}" viewBox="0 0 930 {max(100, 60+40*len(plotted))}"><title>{escape(title)}</title>{"".join(rows)}</svg>'


_MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')
_SEGMENT_COLOR = {'Member': '#1d4e89', 'Casual': '#5c7a6e', 'Classic': '#3d5a4c', 'E-bike': '#6b5b7a', 'Unknown': '#8d8279'}
_SHARE_REASON = {
    'removed': 'Percentage withheld. This month has no trips at this station.',
    'new': 'Percentage withheld. The previous month has no trips at this station.',
    'prior_sample_below_100': 'Share withheld. The previous sample is below 100 trips.',
    'zero_total_change': 'Share withheld. The station total did not change.',
}


def _month_label(period: Period) -> str:
    return f'{_MONTHS[period.month - 1]} {period.year}'


def _whole(number):
    return int(number) if isinstance(number, float) and number.is_integer() else number


def _trips(number) -> str:
    number = _whole(number)
    return f'{"−" if number < 0 else ""}{abs(number):,}'


def _percent(number) -> str:
    return f'{"−" if number < 0 else ""}{abs(float(number)):.2f}%'


def _match(values, metric, *, period=None, other_than=None, dimension=None, category=None, station_level=False):
    found = []
    for value in values:
        if value.metric_type != metric:
            continue
        if station_level and (value.dimension is not None or value.category is not None):
            continue
        if dimension is not None and value.dimension != dimension:
            continue
        if category is not None and value.category != category:
            continue
        if period is not None and value.period != period:
            continue
        if other_than is not None and value.period == other_than:
            continue
        found.append(value)
    return found[0] if len(found) == 1 else None


def _shown_count(value) -> str:
    return 'Unavailable' if value is None or value.exact_tool_value is None else _trips(value.exact_tool_value)


def _segment_panel(values, period, dimension, title, share_name) -> str:
    categories = tuple(category for category in CATEGORIES[dimension] if category != 'Unknown')
    amounts = []
    for category in categories:
        change = _match(values, 'absolute_change', dimension=dimension, category=category)
        amounts.append(None if change is None or change.exact_tool_value is None else abs(change.exact_tool_value))
    scale = max((amount for amount in amounts if amount is not None), default=0)
    rows = []
    for category in categories:
        current = _match(values, 'current_volume', period=period, dimension=dimension, category=category)
        prior = _match(values, 'current_volume', other_than=period, dimension=dimension, category=category)
        change = _match(values, 'absolute_change', dimension=dimension, category=category)
        share = _match(values, 'contribution', dimension=dimension, category=category)
        amount = None if change is None or change.exact_tool_value is None else abs(change.exact_tool_value)
        width = 0 if not scale or amount is None else amount / scale * 100
        if share is not None and share.eligible and share.exact_tool_value is not None:
            share_text = _percent(share.exact_tool_value)
        else:
            reason = None if share is None else share.eligibility_reason
            share_text = _SHARE_REASON.get(reason, 'Share withheld.')
        prior_label = _month_label(prior.period) if prior is not None else 'Previous month'
        rows.append(
            f'<li class="seg"><div class="seg-top"><span class="seg-name">{escape(category)}</span>'
            f'<span>{escape(_shown_count(change))} trips · {escape(share_text)}</span></div>'
            f'<div class="bar" role="img" aria-label="{escape(category)} {escape(_shown_count(change))} trips, {escape(share_text)}">'
            f'<span style="width:{width:.1f}%;background:{_SEGMENT_COLOR[category]}"></span></div>'
            f'<span class="meta">{escape(prior_label)} {escape(_shown_count(prior))} · {escape(_month_label(period))} {escape(_shown_count(current))}</span></li>')
    return (f'<section class="panel" aria-label="{escape(title)}"><h2>{escape(title)}</h2>'
            f'<p class="meta">{escape(share_name)}</p><ul>{"".join(rows)}</ul></section>')


def _station_dashboard(result: ToolResult, period: Period, title: str) -> str:
    """Static station comparison. The month and station are chosen before this report is built."""
    values = result.values
    heading = title.removeprefix('Station starts: ')
    location, station_id = heading, ''
    if heading.endswith(')') and ' (' in heading:
        location, _, station_id = heading.rpartition(' (')
        station_id = station_id[:-1]
    identity = f'<p><strong>Station:</strong> {escape(station_id or location)}</p>'
    if station_id and location != station_id:
        identity += f'<p><strong>Location:</strong> {escape(location)}</p>'
    current_volume = _match(values, 'current_volume', period=period, station_level=True)
    prior_volume = _match(values, 'current_volume', other_than=period, station_level=True)
    change = _match(values, 'absolute_change', station_level=True)
    percentage = _match(values, 'percentage_change', station_level=True)
    current_count = None if current_volume is None else current_volume.exact_tool_value
    prior_count = None if prior_volume is None else prior_volume.exact_tool_value
    delta = None if change is None else change.exact_tool_value
    current_label = _month_label(period)
    prior_label = _month_label(prior_volume.period) if prior_volume is not None else 'Previous month'
    if delta is not None and delta < 0:
        rider_title, bike_title, share_name, change_class = 'Trip loss by rider type', 'Trip loss by bike type', 'Share of lost trips', 'decline'
    elif delta is not None and delta > 0:
        rider_title, bike_title, share_name, change_class = 'Trip gain by rider type', 'Trip gain by bike type', 'Share of added trips', ''
    else:
        rider_title, bike_title, share_name, change_class = 'Rider type', 'Bike type', 'Share of the change', ''
    change_text = 'Unavailable' if delta is None else f'{_trips(delta)} trips'
    if percentage is not None and percentage.eligible and percentage.exact_tool_value is not None:
        change_text += f' ({_percent(percentage.exact_tool_value)})'
        percent_note = ''
    else:
        reason = None if percentage is None else percentage.eligibility_reason
        percent_note = _SHARE_REASON.get(reason, 'Percentage withheld.')
    zero_note = ''
    if current_count == 0 and prior_count not in (None, 0):
        zero_note = (f'<p class="report-note">{escape(current_label)} recorded volume is zero. Investigate whether this reflects '
                     'station removal, closure, or a data issue before attributing the decline to demand.</p>')
    panels = ''.join(_segment_panel(values, period, dimension, panel_title, share_name) for dimension, panel_title in (
        ('member_casual', rider_title), ('rideable_type', bike_title)))
    note = f'<span>{escape(percent_note)}</span>' if percent_note else ''
    return f'''
    <section class="station-dash" aria-label="Station performance">
      {identity}
      <p class="meta">Comparison: {escape(prior_label)} vs. {escape(current_label)}</p>
      <div class="kpis">
        <div class="kpi"><span>{escape(prior_label)} trips</span><strong>{escape(_shown_count(prior_volume))}</strong></div>
        <div class="kpi"><span>{escape(current_label)} trips</span><strong>{escape(_shown_count(current_volume))}</strong></div>
        <div class="kpi {change_class}"><span>Absolute change</span><strong>{escape(change_text)}</strong>{note}</div>
      </div>
      {zero_note}
      <div class="panels">{panels}</div>
      <p class="report-note">Rider type and bike type are separate splits of the same station change. Do not add them together.</p>
    </section>'''


_RANK_LABELS = {
    'total_starts': ('total starts', 'Starts'), 'total_ends': ('total trip ends', 'Trip ends'),
    'ebike_share_pct': ('e-bike share', 'E-bike share (%)'), 'casual_share_pct': ('casual share', 'Casual share (%)'),
    'avg_duration_min': ('average trip duration', 'Average duration (minutes)'),
}
_RANK_FILTERS = {'member': 'members', 'casual': 'casual riders', 'classic_bike': 'classic bikes', 'electric_bike': 'e-bikes'}


def ranking_title(ranking: dict, period: Period) -> str:
    label = _RANK_LABELS[ranking['metric']][0]
    direction = 'Top' if ranking['order'] == 'top' else 'Bottom'
    return f'Station ranking: {direction} {ranking["limit"]} by {label}, {_month_label(period)}'


def ranking_report(ranking: dict, period: Period, *, variance: ToolResult | None = None,
                   chart_svg: str | None = None, narrative: str = '') -> str:
    """Leaderboard from the exact rank_stations payload, then the optional station comparison and verified findings."""
    label, column = _RANK_LABELS[ranking['metric']]
    scope = [_RANK_FILTERS[value] for value in (ranking['filter_by'] or {}).values() if value is not None]
    meta = f'{ranking["eligible_station_count"]:,} stations ranked by {label}'
    meta += f' among {" on ".join(scope)}.' if scope else '.'
    if ranking['minimum_sample'] is not None:
        meta += (f' {ranking["excluded_low_sample_count"]:,} stations with fewer than '
                 f'{ranking["minimum_sample"]} starts were excluded.')
    rows = []
    for row in ranking['rows']:
        notes = ['Tied value'] if row['is_tied'] else []
        if ranking['minimum_sample'] is not None:
            notes.append(f'Meets {ranking["minimum_sample"]}-start minimum')
        rows.append((row['rank'], row['station_id'], row['station_name'], row['metric_value'],
                     row['total_starts'], '; '.join(notes)))
    cards = [kpi_card('Eligible stations', f'{ranking["eligible_station_count"]:,}', label.capitalize()),
             kpi_card('Stations shown', str(len(rows)), f'{ranking["order"].capitalize()} {ranking["limit"]} requested')]
    if ranking['minimum_sample'] is not None:
        cards.append(kpi_card('Minimum sample', f'{ranking["minimum_sample"]:,} starts',
                              f'{ranking["excluded_low_sample_count"]:,} stations excluded'))
    else:
        cards.append(kpi_card('Ranking order', ranking['order'].capitalize(), column))
    leaderboard = (f'<p class="report-note">{escape(meta)}</p>'
                   + _table(('Rank', 'Station ID', 'Station', column, 'Total starts', 'Notes'), rows)
                   + ('<p class="report-note">No station met the ranking rules for this month.</p>' if not rows else ''))
    body = dashboard(_month_label(period), cards)
    body += panel('Station leaderboard', leaderboard)
    if chart_svg:
        body += panel('Ranking chart', '<p class="report-note">Exact values are provided in the table. '
                      'Scroll the chart horizontally on narrow screens.</p>' + _chart_region(chart_svg))
    if variance is not None:
        station = variance.arguments.station_id
        name = next((row['station_name'] for row in ranking['rows'] if row['station_id'] == station), station)
        body += panel('Station comparison', _station_dashboard(variance, period, f'Station starts: {name} ({station})'))
    if narrative:
        body += panel('Verified findings', narrative)
    return _report_document(ranking_title(ranking, period), body)


_METRIC_LABELS = {
    'total_trips': 'Total trips',
    'average_duration': 'Average duration',
    'station_starts': 'Station starts',
    'member_share': 'Rider share',
    'fleet_share': 'Bike share',
}


def _metric_dashboard(result: ToolResult, request: AdhocRequest, chart: str | None) -> str:
    """Present each verified value without adding calculations or implied comparisons."""
    cards, segments = [], []
    for value in result.values:
        category = (value.category or '').replace('Unknown', 'Unknown (unclassified)')
        label = f'{category} share' if category else _METRIC_LABELS[request.metric]
        available = value.eligible and value.exact_tool_value is not None
        unit = '%' if value.unit == 'percent' else f' {value.unit}'
        shown = f'{_display(value.exact_tool_value)}{unit}' if available else 'Unavailable'
        reason = (value.eligibility_reason or '').replace('_', ' ')
        note = _month_label(value.period) + (f' · {reason}' if reason else '')
        cards.append(kpi_card(label, shown, note))
        if category:
            segments.append((category, shown, value.exact_tool_value if available and value.unit == 'percent' else None))
    rows = ((f'{v.period.year:04d}-{v.period.month:02d}', (v.category or v.entity_id).replace('Unknown', 'Unknown (unclassified)'),
             v.metric_type, _display(v.exact_tool_value), v.unit, v.eligibility_reason or '') for v in result.values)
    panels = []
    if segments:
        title = 'Rider type' if request.metric == 'member_share' else 'Bike type'
        panels.append(segment_panel(title, segments, 'Share of trips in the selected month.'))
    panels.append(panel('Exact values', _table(('Month', 'Entity / category', 'Metric', 'Value', 'Unit', 'Eligibility reason'), rows)))
    if chart:
        panels.append(panel('Metric chart', '<p class="report-note">Exact values are provided in the table. '
                            'Scroll the chart horizontally on narrow screens.</p>' + _chart_region(chart)))
    return dashboard(_month_label(request.period), cards, panels)


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

    def run(self, request: AdhocRequest, baseline: BaselineReport | None = None,
            trace: TraceRecorder | None = None) -> AdhocResult:
        trace = trace or TraceRecorder()
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
            trace.record('routing', 'station_lookup', 'Application matched station identifiers and names in the pinned data.',
                         inputs=request.model_dump(mode='json'),
                         output=[choice.model_dump(mode='json') for choice in choices])
            if (request.station_id is None and request.station_query is None) or len(choices) > 1:
                return AdhocResult(status='needs_station_selection', period=request.period,
                    message='Select an explicit station and submit the reporting month again.', station_choices=choices)
            if not choices:
                return self._refusal(request, 'No matching start station exists in the requested months.')
        # Every selected calculation uses the baseline's immutable snapshot, even after replacement.
        refs = baseline.datasets if request.comparison else (baseline.datasets[0],)
        tools = AgentTools(self.store, refs, baseline.report_id, trace=trace)
        available_result, _ = tools.execute('get_available_periods', ToolArguments(), 'adhoc_available')
        result, title = self._calculate(request, refs, tools)
        if result is None:
            return self._refusal(request, title)
        if result.status != 'success':
            return self._refusal(request, 'The requested calculation could not be verified.')
        values = result.values
        station_comparison = request.metric == 'station_starts' and request.comparison and result.tool_name == 'analyze_station_variance'
        chart = None if station_comparison else make_chart(title, result, baseline.report_id) if request.chart else None
        evidence = (available_result, result)
        if chart:
            trace.record('rendering', 'make_chart', 'Application rendered a chart from verified evidence.',
                         inputs=result.model_dump(mode='json'), output={'svg': chart})
            evidence += (result.model_copy(update={'tool_name': 'make_chart', 'tool_call_id': 'adhoc_chart', 'stage': 'rendering'}),)
        if station_comparison:
            body = _station_dashboard(result, request.period, title)
        else:
            body = _metric_dashboard(result, request, chart)
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
                tools.trace.record('execution', 'station_start_count', 'Application counted starts for the resolved station.',
                                   inputs={'station_id': station.station_id, 'dataset': refs[0].model_dump(mode='json')},
                                   output={'total_starts': count})
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
