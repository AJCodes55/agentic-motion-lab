"""Fixed, deterministic dashboard and durable self-contained evidence archive."""
from html import escape
from calendar import month_name
import os
import shutil
from typing import Literal
from uuid import uuid4

from mobility.contracts import Contract, DatasetReference, Period, ToolResult
from mobility.storage import DatasetStore
from mobility.tracing import TraceRecorder
from mobility.report_layout import dashboard, kpi_card, report_document, segment_panel


class BaselineReport(Contract):
    report_id: str
    period: Period
    datasets: tuple[DatasetReference, ...]
    html: str
    evidence: tuple[ToolResult, ...]
    llm_calls: Literal[0] = 0


def _label(value):
    return 'Unknown (unclassified)' if value == 'Unknown' else str(value)


def _table(headers, rows):
    head = ''.join(f'<th scope="col">{escape(str(value))}</th>' for value in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{escape(f'{value:.2f}' if isinstance(value, float) else str(value))}</td>' for value in row) + '</tr>' for row in rows)
    return f'<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable data table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _bars(title, categories):
    rows = []
    for i, item in enumerate(categories):
        y = 28 + i * 32
        rows.append(f'<text x="0" y="{y}">{escape(_label(item.category))}</text><rect x="185" y="{y-15}" width="{item.share*3:.3f}" height="18" fill="#155e75"/><text x="495" y="{y}">{item.share:.2f}% ({item.count})</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{escape(title, quote=True)}" viewBox="0 0 670 130"><title>{escape(title)}</title>{"".join(rows)}</svg>'


def _daily(series):
    max_count = max((day.count for _, trend in series for day in trend.days), default=1) or 1
    # Reserve enough axis space even for large exact trip counts.
    left = max(65, len(str(max_count)) * 9 + 15)
    lines = [f'<text x="{left-10}" y="44" text-anchor="end">{max_count}</text>'
             f'<text x="{left-10}" y="184" text-anchor="end">0</text>']
    lines.extend(f'<text x="{left+(day-1)*19}" y="200">{day}</text>' for day in (1, 10, 20, 31))
    for index, (label, trend) in enumerate(series):
        points = ' '.join(f'{left+(day.day-1)*19},{180-day.count/max_count*140:.3f}' for day in trend.days)
        color = ("#155e75", "#b45309")[index]
        dash = ' stroke-dasharray="7 4"' if index else ''
        style = 'dashed' if index else 'solid'
        legend_y = 220 + index * 20
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="2"{dash} points="{points}"/>'
                     f'<line x1="{left}" x2="{left+30}" y1="{legend_y-5}" y2="{legend_y-5}" stroke="{color}" stroke-width="2"{dash}/>'
                     f'<text x="{left+40}" y="{legend_y}">{escape(label)} ({style})</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Daily starts aligned by day of month; absent calendar days are gaps. Exact values follow in the table." viewBox="0 0 {left+610} 285"><title>Daily start counts</title><text x="230" y="275">Day of month</text>' + ''.join(lines) + '</svg>'


def _archive(store, report, assets):
    root = store.root / 'reports'
    root.mkdir(exist_ok=True)
    staging = root / f'.{report.report_id}.tmp'
    staging.mkdir()
    try:
        files = {'index.html': report.html, 'evidence.json': report.model_dump_json(indent=2), **assets}
        for name, content in files.items():
            with (staging / name).open('x', encoding='utf-8') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        store._sync_directory(staging)
        staging.rename(root / report.report_id)
        store._sync_directory(root)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _quality(store, references):
    blocks = []
    for ref in references:
        meta = store.read_metadata(ref)
        quality = meta['quality']
        fields = ('source_rows', 'invalid_timestamp_rows', 'outside_month_rows', 'duplicate_rows', 'missing_station_rows', 'invalid_duration_rows', 'excluded_rows', 'valid_rows', 'unknown_member_rows', 'unknown_bike_rows')
        rows = [(key.replace('_', ' '), quality[key]) for key in fields]
        coverage = tuple(zip(quality.get('source_filenames', ()), quality.get('per_csv_parsed_counts', ())))
        blocks.append(f'<h3>{ref.period.year:04d}-{ref.period.month:02d}</h3>' + _table(('Quality metric', 'Exact rows'), rows) + '<h4>Source coverage</h4>' + _table(('Source file', 'Parsed rows'), coverage))
    return ''.join(blocks)


def _station_rows(items):
    return tuple((item.station_id, item.station_name, item.current_count, item.prior_count, item.delta, item.percentage_change if item.percentage_change is not None else 'N/A', item.eligible, item.eligibility_reason or '', item.status, item.materiality) for item in items)


def _report_document(title, body):
    """Self-contained readable report; generated HTML content must already be escaped."""
    return report_document(title, body)


def _chart_region(svg):
    return ('<div class="chart-scroll" tabindex="0" role="region" aria-label="Scrollable chart">'
            + svg + '</div>')


def _document(period, sections, summary=''):
    body = summary + ''.join(f'<section class="report-panel"><h2>{escape(title)}</h2>{content}</section>' for title, content in sections)
    return _report_document(f'Monthly mobility baseline: {period.year:04d}-{period.month:02d}', body)


def _signed(number) -> str:
    return f'{"−" if number < 0 else ""}{abs(int(number)):,}'


def _percent_text(number) -> str:
    return f'{"−" if number < 0 else ""}{abs(float(number)):.2f}%'


def _share_panels(summary, label):
    return tuple(segment_panel(title, ((_label(item.category), f'{item.count:,} trips · {item.share:g}%', item.share)
                                       for item in getattr(summary, dimension)), note=f'{label} · Share of trips')
                 for dimension, title in (('member_casual', 'Trips by rider type'), ('rideable_type', 'Trips by bike type')))


def _change_panels(current, prior, total_delta, current_label, prior_label):
    if total_delta < 0:
        rider_title, bike_title, share_name = 'Trip loss by rider type', 'Trip loss by bike type', 'Share of lost trips'
    elif total_delta > 0:
        rider_title, bike_title, share_name = 'Trip gain by rider type', 'Trip gain by bike type', 'Share of added trips'
    else:
        rider_title, bike_title, share_name = 'Rider type', 'Bike type', 'Share of the change'
    panels = []
    for dimension, title, categories in (
            ('member_casual', rider_title, ('Member', 'Casual')),
            ('rideable_type', bike_title, ('Classic', 'E-bike'))):
        now = {item.category: item for item in getattr(current, dimension)}
        before = {item.category: item for item in getattr(prior, dimension)}
        counts = []
        for category in categories:
            current_count = now[category].count if category in now else 0
            prior_count = before[category].count if category in before else 0
            counts.append((category, current_count, prior_count, current_count - prior_count))
        scale = max((abs(delta) for _, _, _, delta in counts), default=0)
        rows = []
        for category, current_count, prior_count, delta in counts:
            if total_delta == 0:
                share_text = 'Share withheld. The total did not change.'
            elif prior_count < 100:
                share_text = 'Share withheld. The previous sample is below 100 trips.'
            else:
                share_text = _percent_text(delta / total_delta * 100)
            width = 0.0 if not scale else min(100.0, abs(delta) / scale * 100)
            rows.append((_label(category), f'{_signed(delta)} trips · {share_text}', width,
                         f'{prior_label} {prior_count:,} · {current_label} {current_count:,}'))
        panels.append(segment_panel(title, rows, note=share_name))
    return tuple(panels)


def _summary_cards(refs, summaries, comparison=None):
    current = summaries[0]
    label = f'{month_name[refs[0].period.month]} {refs[0].period.year}'
    if len(refs) == 2:
        prior = summaries[1]
        prior_label = f'{month_name[refs[1].period.month]} {refs[1].period.year}'
        total = next(metric for metric in comparison.metrics if metric.metric == 'total_trips' and metric.dimension is None)
        change_text = f'{_signed(total.delta)} trips'
        note = ''
        if total.eligible and total.percentage_change is not None:
            change_text += f' ({_percent_text(total.percentage_change)})'
        elif total.eligibility_reason == 'prior_sample_below_100':
            note = 'Share withheld. The previous sample is below 100 trips.'
        elif total.eligibility_reason == 'zero_prior_value':
            note = 'Percentage withheld. The previous month has no trips.'
        else:
            note = 'Percentage withheld.'
        cards = (kpi_card(f'{prior_label} trips', f'{prior.total_trips:,}'),
                 kpi_card(f'{label} trips', f'{current.total_trips:,}'),
                 kpi_card('Absolute change', change_text, note, 'decline' if total.delta < 0 else ''))
        panels = _change_panels(current, prior, total.delta, label, prior_label)
        return dashboard(f'Comparison: {prior_label} vs. {label}', cards, panels,
                         'Rider type and bike type are separate splits of the same change. Do not add them together.')
    average = 'Unavailable' if current.average_duration_minutes is None else f'{current.average_duration_minutes:g} minutes'
    cards = (kpi_card(f'{label} trips', f'{current.total_trips:,}'),
             kpi_card('Average duration', average),
             kpi_card('Reporting month', label, 'Prior month unavailable. Standalone report.'))
    return dashboard(label, cards, _share_panels(current, label))


def generate_standard_dashboard(store: DatasetStore, period: Period,
                                trace: TraceRecorder | None = None) -> BaselineReport:
    from mobility.analytics import AnalyticsService, prior_period
    from mobility.contracts import EvidenceValue, ToolArguments

    trace = trace or TraceRecorder()
    period = Period.model_validate(period)
    try:
        prior = prior_period(period)
    except ValueError:
        prior = None
    available = {item.period for item in store.list_active()}
    periods = (period, prior) if prior in available else (period,)
    refs = store.pin_periods(periods)
    trace.record('baseline', 'dataset_selection', 'Application pinned the selected month and available preceding month.',
                 inputs={'period': period.model_dump(mode='json')},
                 output=[ref.model_dump(mode='json') for ref in refs])
    report_id = uuid4().hex
    service = AnalyticsService(store)
    evidence = []

    def value(ref, entity, metric, exact, unit='trips', **kwargs):
        return EvidenceValue(entity_id=entity, metric_type=metric, period=ref.period, exact_tool_value=exact, unit=unit, eligible=exact is not None, **kwargs)

    def record(tool, datasets, values):
        evidence.append(ToolResult(run_id=report_id, tool_call_id=f'{report_id}_{len(evidence)}', stage='baseline', tool_name=tool, status='success', arguments=ToolArguments(current_period=datasets[0].period, comparison_period=datasets[1].period if len(datasets) == 2 else None), datasets=datasets, values=tuple(values)))

    def calculate(name, *datasets, **kwargs):
        inputs = {'datasets': [ref.model_dump(mode='json') for ref in datasets], **kwargs}
        trace.record('baseline', name, 'Preparing the standard baseline calculation.',
                     status='started', source='application', inputs=inputs)
        try:
            result = getattr(service, name)(*datasets, **kwargs)
        except Exception:
            trace.record('baseline', name, 'Baseline calculation failed.', status='failed', inputs=inputs)
            raise
        trace.record('baseline', name, 'Application calculated baseline metrics.',
                     inputs=inputs, output=result.model_dump(mode='json'))
        return result

    summaries = tuple(calculate('kpi_summary', ref) for ref in refs)
    trends = tuple(calculate('daily_trend', ref) for ref in refs)
    for ref, summary, trend in zip(refs, summaries, trends):
        metrics = [value(ref, 'month', 'trip_count', summary.total_trips), value(ref, 'month', 'average_duration_minutes', summary.average_duration_minutes, 'minutes')]
        for dimension in ('member_casual', 'rideable_type'):
            metrics.extend(value(ref, item.category, metric, exact, unit, dimension=dimension, category=item.category) for item in getattr(summary, dimension) for metric, exact, unit in (('trip_count', item.count, 'trips'), ('share', item.share, 'percent')))
        record('kpi_summary', (ref,), metrics)
        record('daily_trend', (ref,), (value(ref, f'day_{day.day:02d}', 'trip_count', day.count) for day in trend.days))
    score_rows = [(f'{ref.period.year:04d}-{ref.period.month:02d}', summary.total_trips, summary.average_duration_minutes) for ref, summary in zip(refs, summaries)]
    score = _table(('Month', 'Total trips', 'Average duration (minutes)'), score_rows)
    score += ''.join(f'<h3>{dimension.replace("_", " ")}</h3>' + _table(('Category', 'Trips', 'Share (%)'), ((_label(item.category), item.count, item.share) for item in getattr(summaries[0], dimension))) for dimension in ('member_casual', 'rideable_type'))
    comparison = None
    if len(refs) == 2:
        comparison = calculate('compare_periods', *refs)
        change_values = []
        for metric in comparison.metrics:
            kwargs = {'comparison_period': refs[1].period, 'dimension': metric.dimension, 'category': metric.category}
            entity = metric.category or metric.metric
            change_values.extend((
                value(refs[0], entity, 'absolute_change', metric.delta, metric.unit, **kwargs),
                value(refs[0], entity, 'percentage_change', metric.percentage_change, 'percent', eligibility_reason=metric.eligibility_reason, **kwargs),
            ))
        record('compare_periods', refs, change_values)
        score += _table(('Metric', 'Category', 'Current', 'Prior', 'Change', 'Unit', 'Change (%)', 'Eligible', 'Reason', 'Materiality'), (
            (metric.metric, _label(metric.category) if metric.category else '', metric.current_value, metric.prior_value, metric.delta, metric.unit, metric.percentage_change if metric.percentage_change is not None else 'N/A', metric.eligible, metric.eligibility_reason or '', metric.materiality or 'N/A')
            for metric in comparison.metrics))
        movers = calculate('station_movers', *refs)
        station_groups = (('Top five increases', movers.top_5_increases), ('Top five decreases', movers.top_5_decreases))
        station_values = []
        all_items = tuple(item for _, items in station_groups for item in items)
        if movers.mandatory_investigation_candidate is not None:
            all_items += (movers.mandatory_investigation_candidate,)
        unique_items = {item.station_id: item for item in all_items}
        for item in unique_items.values():
            station_values.extend((
                value(refs[0], item.station_id, 'current_volume', item.current_count),
                value(refs[1], item.station_id, 'current_volume', item.prior_count),
                value(refs[0], item.station_id, 'absolute_change', item.delta, comparison_period=refs[1].period),
                value(refs[0], item.station_id, 'percentage_change', item.percentage_change, 'percent', comparison_period=refs[1].period, eligibility_reason=item.eligibility_reason),
            ))
        record('station_movers', refs, station_values)
    else:
        score += '<p>Prior month unavailable. Standalone report; month-over-month comparisons are unavailable.</p>'
        ranking = calculate('station_analysis', refs[0], top_n=5)
        station_groups = (('Top five stations by starts', ranking.stations),)
        record('station_analysis', refs, (value(refs[0], item.station_id, 'trip_count', item.current_count) for item in ranking.stations))
    station_html = ''.join(f'<h3>{title}</h3>' + _table(('Station ID', 'Station', 'Current starts', 'Prior starts', 'Change', 'Change (%)', 'Eligible', 'Eligibility reason', 'Status', 'Materiality'), _station_rows(items)) for title, items in station_groups)
    assets = {'daily.svg': _daily(tuple((f'{ref.period.year:04d}-{ref.period.month:02d}', trend) for ref, trend in zip(refs, trends)))}
    mix = ''
    for ref, summary in zip(refs, summaries):
        mix += f'<h3>{ref.period.year:04d}-{ref.period.month:02d}</h3>'
        for dimension in ('member_casual', 'rideable_type'):
            asset = _bars(dimension.replace('_', ' '), getattr(summary, dimension))
            assets[f'{ref.period.year:04d}_{ref.period.month:02d}_{dimension}.svg'] = asset
            mix += '<h4>' + escape(dimension.replace('_', ' ')) + '</h4>' + _chart_region(asset)
            mix += _table(('Category', 'Trips', 'Share (%)'), ((_label(item.category), item.count, item.share) for item in getattr(summary, dimension)))
    daily = _chart_region(assets['daily.svg']) + '<p>Absent calendar days are gaps, never zero. Exact daily starts:</p>'
    daily += _table(('Month', 'Day of month', 'Starts'), ((f'{ref.period.year:04d}-{ref.period.month:02d}', day.day, day.count) for ref, trend in zip(refs, trends) for day in trend.days))
    sections = (('KPI Scorecard', score), ('Daily Trend', daily), ('Mix Breakdowns', mix), ('Top Stations / Movers', station_html), ('Data-Quality Summary', _quality(store, refs)))
    report = BaselineReport(report_id=report_id, period=period, datasets=refs,
                            html=_document(period, sections, _summary_cards(refs, summaries, comparison)),
                            evidence=tuple(evidence))
    _archive(store, report, assets)
    trace.record('baseline', 'baseline_rendering', 'Application rendered and archived the standard baseline.',
                 output={'report_id': report.report_id})
    return report
