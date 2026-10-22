import json

import pytest
from pydantic import ValidationError

from mobility.adhoc import AdhocRequest, AdhocService
from mobility.contracts import Period, QualitySummary
from mobility.storage import DatasetStore
from test_analytics import fixture


@pytest.mark.parametrize('metric', ['total_trips', 'member_share', 'fleet_share', 'average_duration'])
def test_monthly_metrics_chart_archive_and_replacement(tmp_path, metric):
    store = DatasetStore(tmp_path)
    ref = fixture(store, 2, {'S': 120})
    result = AdhocService(store).run(AdhocRequest(period=ref.period, metric=metric, chart=True))
    assert result.status == 'success'
    assert result.datasets == (ref,)
    assert result.chart_svg and result.chart_svg in result.html
    assert result.evidence[-1].tool_name == 'make_chart'
    assert result.evidence[-1].values == result.evidence[-2].values
    archived = tmp_path / 'reports' / result.report_id
    assert (archived / 'adhoc.html').read_text() == result.html
    saved = (archived / 'adhoc.json').read_text()
    fixture(store, 2, {'S': 5})
    assert (archived / 'adhoc.json').read_text() == saved
    assert json.loads(saved)['datasets'][0]['version_id'] == ref.version_id


def test_station_missing_context_ambiguity_lookup_and_no_top_five_limit(tmp_path):
    store = DatasetStore(tmp_path)
    ref = fixture(store, 2, {f'S{i}': 10 + i for i in range(8)})
    service = AdhocService(store)
    assert service.run(AdhocRequest(period=ref.period, metric='station_starts')).status == 'needs_station_selection'
    assert service.run(AdhocRequest(period=ref.period, metric='station_starts', station_query='S')).status == 'needs_station_selection'
    result = service.run(AdhocRequest(period=ref.period, metric='station_starts', station_id='S0'))
    assert result.status == 'success'
    assert result.evidence[-1].values[0].exact_tool_value == 10
    assert service.run(AdhocRequest(period=ref.period, metric='station_starts', station_id='absent')).status == 'refused'


def test_adjacent_station_comparison_missing_prior_and_nonadjacent(tmp_path):
    store = DatasetStore(tmp_path)
    ref = fixture(store, 2, {'S': 80})
    service = AdhocService(store)
    request = AdhocRequest(period=ref.period, metric='station_starts', station_id='S', comparison=True)
    assert service.run(request).status == 'refused'
    prior = fixture(store, 1, {'S': 100})
    result = service.run(request)
    assert result.status == 'success'
    assert result.datasets == (ref, prior)
    assert result.evidence[-1].tool_name == 'analyze_station_variance'
    assert any(v.exact_tool_value == -20 for v in result.evidence[-1].values)
    assert service.run(request.model_copy(update={'comparison_period': Period(year=2025, month=12)})).status == 'refused'


def test_strict_catalog_and_explicit_period(tmp_path):
    with pytest.raises(ValidationError):
        AdhocRequest(metric='total_trips')
    with pytest.raises(ValidationError):
        AdhocRequest(period=Period(year=2026, month=2), metric='forecast')
    store = DatasetStore(tmp_path)
    assert AdhocService(store).run(AdhocRequest(period=Period(year=2026, month=2), metric='total_trips')).status == 'refused'


def test_reuse_baseline_snapshot_and_reject_aggregate_comparison(tmp_path):
    from mobility.baseline import generate_standard_dashboard
    store = DatasetStore(tmp_path)
    prior = fixture(store, 1, {'S': 100})
    current = fixture(store, 2, {'S': 80})
    baseline = generate_standard_dashboard(store, current.period)
    fixture(store, 2, {'S': 3})
    result = AdhocService(store).run(AdhocRequest(period=current.period, metric='station_starts', station_id='S', comparison=True), baseline=baseline)
    assert result.datasets == (current, prior)
    assert result.evidence[1].values[0].exact_tool_value == 80
    assert AdhocService(store).run(AdhocRequest(period=current.period, metric='total_trips', comparison=True)).status == 'refused'


def test_chart_rejects_wrong_run_failed_or_wrong_period_evidence(tmp_path):
    from mobility.adhoc import make_chart
    store = DatasetStore(tmp_path)
    ref = fixture(store, 2, {'S': 2})
    result = AdhocService(store).run(AdhocRequest(period=ref.period, metric='total_trips'))
    source = result.evidence[-1]
    with pytest.raises(ValueError):
        make_chart('title', source, 'another_run')
    with pytest.raises(ValueError):
        make_chart('title', source.model_copy(update={'status': 'failed'}), result.report_id)
    wrong_value = source.values[0].model_copy(update={'period': Period(year=2026, month=3)})
    with pytest.raises(ValueError):
        make_chart('title', source.model_copy(update={'values': (wrong_value,)}), result.report_id)


def test_duplicate_station_names_require_selection_and_escape_names(tmp_path):
    from types import SimpleNamespace
    store = DatasetStore(tmp_path)
    ref = fixture(store, 2, {'A': 3, 'B': 2})
    frame = store.read_frame(ref).assign(start_station_name='<script>Harbor</script>')
    quality = QualitySummary(source_rows=5, valid_rows=5, excluded_rows=0)
    ref = store.persist_and_activate(SimpleNamespace(period=ref.period, frame=frame, quality=quality, sources=()))
    service = AdhocService(store)
    result = service.run(AdhocRequest(period=ref.period, metric='station_starts', station_query='<script>Harbor</script>'))
    assert result.status == 'needs_station_selection'
    assert [choice.station_id for choice in result.station_choices] == ['A', 'B']
    result = service.run(AdhocRequest(period=ref.period, metric='station_starts', station_id='B', chart=True))
    assert result.status == 'success'
    assert '<script>' not in result.html
    assert '&lt;script&gt;' in result.html


def test_archive_failure_removes_partial_ad_hoc_artifacts(tmp_path, monkeypatch):
    from pathlib import Path
    store = DatasetStore(tmp_path)
    ref = fixture(store, 2, {'S': 2})
    service = AdhocService(store)
    result = service.run(AdhocRequest(period=ref.period, metric='total_trips', chart=True))
    new_root = tmp_path / 'reports' / 'new_archive'
    new_root.mkdir()
    original = Path.rename
    def fail_chart(path, target):
        if path.name == '.adhoc-chart.svg.tmp':
            raise OSError('disk failure')
        return original(path, target)
    monkeypatch.setattr(Path, 'rename', fail_chart)
    with pytest.raises(OSError):
        service._persist(result.model_copy(update={'report_id': 'new_archive'}))
    assert list(new_root.iterdir()) == []


def test_whitespace_station_query_cannot_select_only_station_by_default():
    with pytest.raises(ValidationError):
        AdhocRequest(period=Period(year=2026, month=2), metric='station_starts', station_query='   ')
