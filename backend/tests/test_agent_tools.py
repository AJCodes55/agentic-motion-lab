from types import SimpleNamespace

import pandas as pd

from mobility.agent_tools import AgentTools
from mobility.contracts import Period, QualitySummary, ToolArguments
from mobility.storage import DatasetStore


def _month(store, month, station_counts):
    rows = []
    for station, count in station_counts.items():
        rows.extend({'started_at': f'2026-{month:02d}-03 12:00:00', 'duration_seconds': 600,
                     'start_station_id': station, 'start_station_name': station,
                     'member_casual': 'Member' if i % 2 else 'Casual',
                     'rideable_type': 'Classic' if i % 3 else 'E-bike'} for i in range(count))
    total = len(rows)
    return store.persist_and_activate(SimpleNamespace(period=Period(year=2026, month=month),
        frame=pd.DataFrame(rows), quality=QualitySummary(source_rows=total, valid_rows=total, excluded_rows=0)))


def test_pinned_dispatch_and_aggregate_only_payload(tmp_path):
    store = DatasetStore(tmp_path)
    prior = _month(store, 1, {'A': 300, 'B': 200})
    current = _month(store, 2, {'A': 120, 'B': 220})
    tools = AgentTools(store, (current, prior), 'run')
    args = ToolArguments(current_period=current.period, comparison_period=prior.period)
    movers, payload = tools.execute('station_movers', args, 'c1')
    assert movers.status == 'success'
    assert movers.datasets == (current, prior)
    assert payload['mandatory_investigation_candidate']['station_id'] == 'A'
    assert all('started_at' not in str(value) for value in payload.values())
    variance, detail = tools.execute('analyze_station_variance',
        ToolArguments(current_period=current.period, comparison_period=prior.period, station_id='A'), 'c2')
    assert variance.status == 'success'
    assert {'member_casual', 'rideable_type'} <= detail.keys()
    assert any(value.metric_type == 'contribution' and value.dimension == 'member_casual' for value in variance.values)
    assert any(value.eligibility_reason == 'prior_sample_below_100' for value in variance.values)


def test_rejects_wrong_period_unpinned_data_and_extra_arguments(tmp_path):
    store = DatasetStore(tmp_path)
    prior = _month(store, 1, {'A': 200})
    current = _month(store, 2, {'A': 220})
    tools = AgentTools(store, (current,), 'run')
    for name, args in (
        ('compare_periods', ToolArguments(current_period=current.period, comparison_period=prior.period)),
        ('kpi_summary', ToolArguments(current_period=prior.period)),
        ('kpi_summary', ToolArguments(current_period=current.period, station_id='A')),
        ('make_chart', ToolArguments(current_period=current.period)),
    ):
        result, payload = tools.execute(name, args, 'bad')
        assert result.status == 'failed'
        assert result.values == ()
        assert payload == {}


def test_all_supported_operations_return_evidence_and_pinned_data(tmp_path):
    store = DatasetStore(tmp_path)
    prior = _month(store, 1, {'A': 200})
    current = _month(store, 2, {'A': 220})
    tools = AgentTools(store, (current, prior), 'run')
    cases = (
        ('get_available_periods', ToolArguments()),
        ('retrieve_context', ToolArguments()),
        ('kpi_summary', ToolArguments(current_period=current.period)),
        ('compare_periods', ToolArguments(current_period=current.period, comparison_period=prior.period)),
        ('station_analysis', ToolArguments(current_period=current.period, top_n=1)),
        ('station_movers', ToolArguments(current_period=current.period, comparison_period=prior.period)),
        ('analyze_station_variance', ToolArguments(current_period=current.period,
            comparison_period=prior.period, station_id='A')),
    )
    for name, args in cases:
        evidence, payload = tools.execute(name, args, name)
        assert evidence.status == 'success', evidence.validation_reason
        assert evidence.arguments == args
        assert payload
        assert evidence.datasets[0] == current
    assert tools.execute('get_available_periods', ToolArguments(), 'list')[1]['datasets'] == [
        current.model_dump(mode='json'), prior.model_dump(mode='json')]


def test_failed_tool_does_not_expose_filesystem_path(tmp_path, monkeypatch):
    store = DatasetStore(tmp_path)
    current = _month(store, 2, {'A': 2})
    tools = AgentTools(store, (current,), 'run')
    private_path = '/private/users/example/secret/cleaned.csv'
    monkeypatch.setattr(store, 'read_frame', lambda *_: (_ for _ in ()).throw(OSError(private_path)))
    result, payload = tools.execute('station_analysis', ToolArguments(current_period=current.period), 'call')
    assert result.status == 'failed' and payload == {}
    assert private_path not in result.model_dump_json()
    assert result.validation_reason == 'Tool execution failed.'
