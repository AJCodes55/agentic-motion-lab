import json
from types import SimpleNamespace

import pandas as pd

from mobility.baseline import generate_standard_dashboard
from mobility.contracts import Period, QualitySummary
from mobility.storage import DatasetStore


def publish(store, month=1, name='<script>alert(1)</script>'):
    frame = pd.DataFrame({'ride_id': ['a', 'b'], 'started_at': [f'2026-{month:02d}-01 10:00:00', f'2026-{month:02d}-02 10:00:00'], 'start_station_id': ['x', 'y'], 'start_station_name': [name, 'Y'], 'member_casual': ['Member', 'Unknown'], 'rideable_type': ['Classic', 'E-bike'], 'duration_seconds': [60., 120.]})
    return store.persist_and_activate(SimpleNamespace(period=Period(year=2026, month=month), frame=frame, quality=QualitySummary(source_rows=2, valid_rows=2, excluded_rows=0), sources=()))


def test_standalone_archive_escaped_and_survives_replacement(tmp_path):
    store = DatasetStore(tmp_path)
    ref = publish(store)
    report = generate_standard_dashboard(store, ref.period)
    archive = tmp_path / 'reports' / report.report_id
    assert report.llm_calls == 0
    assert report.datasets == (ref,)
    assert len(report.evidence) >= 3
    assert report.html.count('<section') == 5
    assert 'Prior month unavailable' in report.html
    assert '<script>' not in report.html
    assert '&lt;script&gt;' in report.html
    assert 'Unknown (unclassified)' in report.html
    assert '<svg' in report.html
    assert (archive / 'index.html').read_text() == report.html
    assert json.loads((archive / 'evidence.json').read_text())['datasets'][0]['version_id'] == ref.version_id
    publish(store, name='Replacement')
    assert (archive / 'index.html').read_text() == report.html


def test_comparison_archive_and_pinned_evidence(tmp_path):
    store = DatasetStore(tmp_path)
    prior = publish(store)
    current = publish(store, month=2)
    report = generate_standard_dashboard(store, current.period)
    assert report.datasets == (current, prior)
    assert 'Prior month unavailable' not in report.html
    assert 'Top five increases' in report.html
    assert 'Day of month' in report.html
    assert all(item.datasets for item in report.evidence)
    assert all(item.tool_name != 'analyze_station_variance' for item in report.evidence)


def test_archive_failure_does_not_publish(tmp_path, monkeypatch):
    import pytest
    import mobility.baseline as baseline
    store = DatasetStore(tmp_path)
    ref = publish(store)
    monkeypatch.setattr(baseline.os, 'fsync', lambda descriptor: (_ for _ in ()).throw(OSError('disk failure')))
    with pytest.raises(OSError, match='disk failure'):
        generate_standard_dashboard(store, ref.period)
    assert list((tmp_path / 'reports').iterdir()) == []


def test_both_periods_pinned_once(tmp_path, monkeypatch):
    store = DatasetStore(tmp_path)
    prior = publish(store)
    current = publish(store, month=2)
    original = store.pin_periods
    calls = []
    def pin(periods):
        calls.append(periods)
        return original(periods)
    monkeypatch.setattr(store, 'pin_periods', pin)
    generate_standard_dashboard(store, current.period)
    assert calls == [(current.period, prior.period)]


def test_comparison_low_volume_percentage_unavailable_and_full_station_evidence(tmp_path):
    store = DatasetStore(tmp_path)
    publish(store)
    current = publish(store, month=2)
    report = generate_standard_dashboard(store, current.period)
    comparison = next(item for item in report.evidence if item.tool_name == 'compare_periods')
    percentages = [item for item in comparison.values if item.metric_type == 'percentage_change']
    assert percentages
    assert all(item.exact_tool_value is None and not item.eligible and item.eligibility_reason for item in percentages)
    movers = next(item for item in report.evidence if item.tool_name == 'station_movers')
    # Equal station volumes have no displayed movers; all displayed values still remain grounded.
    assert all(item.metric_type in ('current_volume', 'absolute_change', 'percentage_change') for item in movers.values)
    assert 'N/A' in report.html


def test_mover_evidence_keeps_both_counts_delta_and_eligibility(tmp_path):
    store = DatasetStore(tmp_path)
    for month, count in ((1, 120), (2, 60)):
        frame = pd.DataFrame({'ride_id': [f'{i}' for i in range(count)], 'started_at': [f'2026-{month:02d}-01 10:00:00'] * count, 'start_station_id': ['x'] * count, 'start_station_name': ['X'] * count, 'member_casual': ['Member'] * count, 'rideable_type': ['Classic'] * count, 'duration_seconds': [60.] * count})
        period = Period(year=2026, month=month)
        store.persist_and_activate(SimpleNamespace(period=period, frame=frame, quality=QualitySummary(source_rows=count, valid_rows=count, excluded_rows=0), sources=()))
    report = generate_standard_dashboard(store, period)
    result = next(item for item in report.evidence if item.tool_name == 'station_movers')
    values = {(item.period.month, item.metric_type): item.exact_tool_value for item in result.values}
    assert values == {(2, 'current_volume'): 60, (1, 'current_volume'): 120, (2, 'absolute_change'): -60, (2, 'percentage_change'): -50.0}


def test_report_has_keyboard_scroll_regions_and_column_headers(tmp_path):
    store = DatasetStore(tmp_path)
    ref = publish(store)
    report = generate_standard_dashboard(store, ref.period)
    assert '<main id="report-content">' in report.html
    assert '<th scope="col">' in report.html
    assert 'tabindex="0" role="region" aria-label="Scrollable data table"' in report.html
    assert 'overflow-x:auto' in report.html
    assert ':focus-visible' in report.html


def test_comparison_chart_has_exact_tables_and_noncolor_legend(tmp_path):
    store = DatasetStore(tmp_path)
    publish(store)
    current = publish(store, month=2)
    report = generate_standard_dashboard(store, current.period)
    daily = report.html.split('<h2>Daily Trend</h2>')[1].split('</section>')[0]
    assert '<th scope="col">Day of month</th>' in daily
    assert '<td>2026-01</td><td>31</td><td>0</td>' in daily
    assert '<td>2026-02</td><td>28</td><td>0</td>' in daily
    assert '<td>2026-02</td><td>29</td>' not in daily
    assert 'stroke-dasharray="7 4"' in daily
    assert '2026-01 (dashed)' in daily
    mix = report.html.split('<h2>Mix Breakdowns</h2>')[1].split('</section>')[0]
    assert mix.count('<th scope="col">Share (%)</th>') == 4
    assert mix.count('<td>Unknown (unclassified)</td>') == 4
