"""Independent fixed Python comparator over the agent's pinned cleaned snapshot."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from mobility.baseline import generate_standard_dashboard
from mobility.contracts import Period, QualitySummary
from mobility.storage import DatasetStore


@pytest.fixture
def reference_baseline():
    path = Path(__file__).resolve().parents[2] / 'Baseline Python Script v2.py'
    spec = importlib.util.spec_from_file_location('reference_baseline_v2', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def publish(store, month, stations):
    rows = [dict(ride_id=f'{month}-{station}-{index}',
                 started_at=f'2026-{month:02d}-01 10:00:00', start_station_id=station,
                 start_station_name='Shared Name' if station in ('001', '002') else station,
                 member_casual='Member', rideable_type='Classic', duration_seconds=120.0)
            for station, count in stations.items() for index in range(count)]
    return store.persist_and_activate(SimpleNamespace(
        period=Period(year=2026, month=month), frame=pd.DataFrame(rows),
        quality=QualitySummary(source_rows=len(rows), valid_rows=len(rows), excluded_rows=0),
        sources=()))


@pytest.fixture
def snapshot(tmp_path):
    root = tmp_path / 'data'
    store = DatasetStore(root)
    publish(store, 1, dict.fromkeys(('001', '002', '010', 'A', 'B', 'C'), 1))
    current = publish(store, 2, {'001': 2, '002': 1, '010': 1, 'A': 1, 'B': 1, 'C': 1})
    report = generate_standard_dashboard(store, current.period)
    path = root / 'reports' / report.report_id / 'evidence.json'
    return root, report, path


def inventory(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


def test_same_name_ids_remain_distinct_and_ties_keep_string_identifiers(reference_baseline, snapshot):
    root, report, _ = snapshot
    before = inventory(root)
    result = reference_baseline.calculate(reference_baseline.ReadOnlyStore(root), report)
    assert result['monthly_totals'] == {'2026-01': 6, '2026-02': 7}
    stations = result['top_stations']
    assert [item['station_id'] for item in stations] == ['001', '002', '010', 'A', 'B']
    assert [item['ride_count'] for item in stations] == [3, 2, 2, 2, 2]
    assert stations[0]['station_name'] == stations[1]['station_name'] == 'Shared Name'
    assert inventory(root) == before


def test_missing_reporting_month_is_refused(reference_baseline, tmp_path):
    root = tmp_path / 'data'
    store = DatasetStore(root)
    january = publish(store, 1, {'001': 1})
    report = generate_standard_dashboard(store, january.period)
    with pytest.raises(ValueError):
        reference_baseline.calculate(reference_baseline.ReadOnlyStore(root), report)


def test_changed_cleaned_bytes_are_rejected(reference_baseline, snapshot):
    root, report, _ = snapshot
    ref = report.datasets[0]
    path = root / 'versions' / ref.version_id / 'cleaned.csv'
    path.chmod(0o644)
    path.write_bytes(path.read_bytes() + b'\n')
    before = inventory(root)
    with pytest.raises(ValueError, match='checksum'):
        reference_baseline.calculate(reference_baseline.ReadOnlyStore(root), report)
    assert inventory(root) == before


def test_expired_versions_refused_without_resetting_upload_clock(reference_baseline, snapshot):
    root, report, _ = snapshot
    with closing(sqlite3.connect(root / 'registry.sqlite')) as db, db:
        db.execute('UPDATE retention SET uploaded_at=?',
                   (datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat(),))
    before = inventory(root)
    with pytest.raises((ValueError, KeyError)):
        reference_baseline.calculate(reference_baseline.ReadOnlyStore(root), report)
    assert inventory(root) == before


def test_missing_store_is_not_created(reference_baseline, tmp_path):
    missing = tmp_path / 'missing'
    with pytest.raises((ValueError, FileNotFoundError)):
        reference_baseline.ReadOnlyStore(missing)
    assert not missing.exists()


def test_existing_output_is_preserved(reference_baseline, snapshot, tmp_path):
    root, _, evidence = snapshot
    output = tmp_path / 'existing-output'
    output.mkdir()
    sentinel = output / 'preserve.txt'
    sentinel.write_text('preserve')
    before = inventory(root)
    with pytest.raises((ValueError, FileExistsError)):
        reference_baseline.run(root, evidence, output)
    assert sentinel.read_text() == 'preserve'
    assert inventory(root) == before


def test_excel_json_results_and_source_inventory_match(reference_baseline, snapshot, tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    root, report, evidence = snapshot
    output = tmp_path / 'new-output'
    before = inventory(root)
    result = reference_baseline.run(root, evidence, output)
    saved = json.loads((output / 'baseline.json').read_text())
    assert saved == result
    assert saved['monthly_totals'] == {'2026-01': 6, '2026-02': 7}
    workbook = openpyxl.load_workbook(output / 'Citi_Bike_Winter_2026_Basic_Report.xlsx')
    values = [cell.value for row in workbook.active for cell in row]
    assert '001' in values and '002' in values
    assert 6 in values and 7 in values
    assert len(workbook.active._charts) == 1
    workbook.close()
    assert inventory(root) == before
    assert {ref['version_id'] for ref in saved['datasets']} == {ref.version_id for ref in report.datasets}


def test_snapshot_keeps_original_versions_after_replacement(reference_baseline, snapshot):
    root, report, _ = snapshot
    store = DatasetStore(root)
    publish(store, 1, {'replacement': 1})
    publish(store, 2, {'replacement': 1})
    before = inventory(root)
    result = reference_baseline.calculate(reference_baseline.ReadOnlyStore(root), report)
    assert result['monthly_totals'] == {'2026-01': 6, '2026-02': 7}
    assert [station['station_id'] for station in result['top_stations']] == ['001', '002', '010', 'A', 'B']
    assert inventory(root) == before


def test_calculations_do_not_reuse_production_analytics(reference_baseline, snapshot, monkeypatch):
    from mobility.analytics import AnalyticsService

    def forbidden(*args, **kwargs):
        raise AssertionError('Independent baseline must aggregate the cleaned rows itself')

    monkeypatch.setattr(AnalyticsService, 'kpi_summary', forbidden)
    monkeypatch.setattr(AnalyticsService, 'station_analysis', forbidden)
    root, report, _ = snapshot
    result = reference_baseline.calculate(reference_baseline.ReadOnlyStore(root), report)
    assert result['monthly_totals'] == {'2026-01': 6, '2026-02': 7}


def test_formula_like_labels_are_excel_text(reference_baseline, tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    root = tmp_path / 'data'
    store = DatasetStore(root)
    publish(store, 1, {'=2+2': 1})
    current = publish(store, 2, {'=2+2': 1})
    report = generate_standard_dashboard(store, current.period)
    evidence = root / 'reports' / report.report_id / 'evidence.json'
    output = tmp_path / 'formula-output'
    reference_baseline.run(root, evidence, output)
    workbook = openpyxl.load_workbook(output / 'Citi_Bike_Winter_2026_Basic_Report.xlsx')
    for column in (2, 3):
        cell = workbook.active.cell(10, column)
        assert cell.value == '=2+2'
        assert cell.data_type == 's'
    workbook.close()


def test_output_cannot_be_created_in_working_store(reference_baseline, snapshot):
    root, _, evidence = snapshot
    before = inventory(root)
    with pytest.raises(ValueError, match='outside'):
        reference_baseline.run(root, evidence, root / 'baseline-output')
    assert not (root / 'baseline-output').exists()
    assert inventory(root) == before
