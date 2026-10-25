"""Fixed, deterministic dashboard and durable self-contained evidence archive."""
from html import escape
import os
import shutil
from typing import Literal
from uuid import uuid4

from mobility.contracts import Contract, DatasetReference, Period, ToolResult
from mobility.storage import DatasetStore


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
    styles = """body{font:16px/1.6 system-ui;max-width:1100px;margin:1rem auto;padding:1rem;color:#172a36;background:#fff}
    main{min-width:0}h1{font-size:clamp(1.5rem,4vw,2rem);line-height:1.25;overflow-wrap:anywhere}
    h2{line-height:1.35}section{margin:2rem 0}table{border-collapse:collapse;width:100%;min-width:36rem}
    th,td{border:1px solid #ccd4da;padding:.65rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}
    th{background:#eef3f5}tbody tr:nth-child(even){background:#f7fafb}
    .table-scroll,.chart-scroll{overflow-x:auto;margin:1rem 0;max-width:100%}
    :focus-visible{outline:3px solid #155e75;outline-offset:3px}
    svg{display:block;width:100%;min-width:670px;height:auto;font:14px system-ui}
    .report-note{color:#425563;font-size:.95rem}
    @media(max-width:600px){body{margin:0;padding:.75rem}th,td{padding:.5rem}}
    @media print{body{max-width:none;margin:0}.table-scroll,.chart-scroll{overflow:visible}table{min-width:0}svg{min-width:0}}
    """
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(title)}</title><style>{styles}</style></head><body>'
            f'<main id="report-content"><h1>{escape(title)}</h1>{body}</main></body></html>')


def _chart_region(svg):
    return ('<div class="chart-scroll" tabindex="0" role="region" aria-label="Scrollable chart">'
            + svg + '</div>')


def _document(period, sections):
    body = ''.join(f'<section><h2>{escape(title)}</h2>{content}</section>' for title, content in sections)
    return _report_document(f'Monthly mobility baseline: {period.year:04d}-{period.month:02d}', body)


def generate_standard_dashboard(store: DatasetStore, period: Period) -> BaselineReport:
    from mobility.analytics import AnalyticsService, prior_period
    from mobility.contracts import EvidenceValue, ToolArguments

    period = Period.model_validate(period)
    try:
        prior = prior_period(period)
    except ValueError:
        prior = None
    available = {item.period for item in store.list_active()}
    periods = (period, prior) if prior in available else (period,)
    refs = store.pin_periods(periods)
    report_id = uuid4().hex
    service = AnalyticsService(store)
    evidence = []

    def value(ref, entity, metric, exact, unit='trips', **kwargs):
        return EvidenceValue(entity_id=entity, metric_type=metric, period=ref.period, exact_tool_value=exact, unit=unit, eligible=exact is not None, **kwargs)

    def record(tool, datasets, values):
        evidence.append(ToolResult(run_id=report_id, tool_call_id=f'{report_id}_{len(evidence)}', stage='baseline', tool_name=tool, status='success', arguments=ToolArguments(current_period=datasets[0].period, comparison_period=datasets[1].period if len(datasets) == 2 else None), datasets=datasets, values=tuple(values)))

    summaries = tuple(service.kpi_summary(ref) for ref in refs)
    trends = tuple(service.daily_trend(ref) for ref in refs)
    for ref, summary, trend in zip(refs, summaries, trends):
        metrics = [value(ref, 'month', 'trip_count', summary.total_trips), value(ref, 'month', 'average_duration_minutes', summary.average_duration_minutes, 'minutes')]
        for dimension in ('member_casual', 'rideable_type'):
            metrics.extend(value(ref, item.category, metric, exact, unit, dimension=dimension, category=item.category) for item in getattr(summary, dimension) for metric, exact, unit in (('trip_count', item.count, 'trips'), ('share', item.share, 'percent')))
        record('kpi_summary', (ref,), metrics)
        record('daily_trend', (ref,), (value(ref, f'day_{day.day:02d}', 'trip_count', day.count) for day in trend.days))
    score_rows = [(f'{ref.period.year:04d}-{ref.period.month:02d}', summary.total_trips, summary.average_duration_minutes) for ref, summary in zip(refs, summaries)]
    score = _table(('Month', 'Total trips', 'Average duration (minutes)'), score_rows)
    score += ''.join(f'<h3>{dimension.replace("_", " ")}</h3>' + _table(('Category', 'Trips', 'Share (%)'), ((_label(item.category), item.count, item.share) for item in getattr(summaries[0], dimension))) for dimension in ('member_casual', 'rideable_type'))
    if len(refs) == 2:
        comparison = service.compare_periods(*refs)
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
        movers = service.station_movers(*refs)
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
        ranking = service.station_analysis(refs[0], top_n=5)
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
    report = BaselineReport(report_id=report_id, period=period, datasets=refs, html=_document(period, sections), evidence=tuple(evidence))
    _archive(store, report, assets)
    return report
