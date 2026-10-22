"""Archive browsing preserves pinned reports and rejects unsafe paths."""
import json

import pytest

from mobility.baseline import generate_standard_dashboard
from mobility.contracts import Period
from mobility.history import list_report_history, read_archived_report
from mobility.storage import DatasetStore
from test_baseline import publish


def test_empty_history(tmp_path):
    assert list_report_history(DatasetStore(tmp_path)) == ()


def test_baseline_history_survives_dataset_replacement(tmp_path):
    store = DatasetStore(tmp_path)
    reference = publish(store)
    report = generate_standard_dashboard(store, reference.period)
    publish(store, name='Corrected station')
    entry, = list_report_history(store)
    assert entry.report_id == report.report_id
    assert entry.report_kind == 'baseline'
    assert entry.status == 'complete'
    assert entry.datasets == (reference,)
    assert read_archived_report(store, entry.report_id) == report.html


def test_committed_agent_report_is_preferred(tmp_path):
    store = DatasetStore(tmp_path)
    reference = publish(store)
    report = generate_standard_dashboard(store, reference.period)
    directory = tmp_path / 'reports' / report.report_id / 'agent'
    directory.mkdir()
    payload = dict(run_id=report.report_id, status='partial', period=reference.period.model_dump(),
                   datasets=[reference.model_dump()], report_html='<html>Archived agent</html>',
                   warning='Service unavailable', error_code='ERR_LLM_UNAVAILABLE', stages=[], trace=[],
                   counters=dict(llm_calls=0, tool_calls=0, input_tokens=0, output_tokens=0))
    (directory / 'agent-run.json').write_text(json.dumps(payload))
    (directory / 'index.html').write_text(payload['report_html'])
    entry, = list_report_history(store)
    assert (entry.report_kind, entry.status) == ('agent', 'partial')
    assert read_archived_report(store, report.report_id) == payload['report_html']


@pytest.mark.parametrize('report_id', ['../registry.sqlite', '.', '/tmp', 'a/b', 'a' * 33, '%2e%2e', ''])
def test_invalid_archive_identifiers(tmp_path, report_id):
    with pytest.raises(ValueError, match='Invalid report ID'):
        read_archived_report(DatasetStore(tmp_path), report_id)


def test_missing_and_unpublished_archives(tmp_path):
    store = DatasetStore(tmp_path)
    (tmp_path / 'reports').mkdir()
    (tmp_path / 'reports' / '.pending.tmp').mkdir()
    assert list_report_history(store) == ()
    with pytest.raises(KeyError):
        read_archived_report(store, 'a' * 32)


def test_symlink_escape_is_rejected(tmp_path):
    store = DatasetStore(tmp_path / 'store')
    reports = store.root / 'reports'
    reports.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'index.html').write_text('private')
    (reports / ('a' * 32)).symlink_to(outside, target_is_directory=True)
    assert list_report_history(store) == ()
    with pytest.raises(ValueError, match='Unsafe archive path'):
        read_archived_report(store, 'a' * 32)


def test_metadata_identity_and_html_integrity_are_checked(tmp_path):
    store = DatasetStore(tmp_path)
    reference = publish(store)
    report = generate_standard_dashboard(store, reference.period)
    directory = tmp_path / 'reports' / report.report_id
    (directory / 'index.html').write_text('tampered')
    with pytest.raises(ValueError, match='Archived HTML'):
        read_archived_report(store, report.report_id)


def test_file_symlink_and_metadata_identity_rejected(tmp_path):
    store = DatasetStore(tmp_path)
    reference = publish(store)
    report = generate_standard_dashboard(store, reference.period)
    directory = tmp_path / 'reports' / report.report_id
    metadata = json.loads((directory / 'evidence.json').read_text())
    metadata['report_id'] = 'b' * 32
    (directory / 'evidence.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='identity mismatch'):
        list_report_history(store)
    metadata['report_id'] = report.report_id
    (directory / 'evidence.json').write_text(json.dumps(metadata))
    (directory / 'index.html').unlink()
    (directory / 'index.html').symlink_to(directory / 'evidence.json')
    with pytest.raises(ValueError, match='Unsafe archive path'):
        read_archived_report(store, report.report_id)


def test_adhoc_report_is_preferred_and_keeps_pinned_references(tmp_path):
    from mobility.adhoc import AdhocRequest, AdhocService

    store = DatasetStore(tmp_path)
    publish(store, month=1)
    reference = publish(store, month=2)
    result = AdhocService(store).run(AdhocRequest(period=reference.period, metric='total_trips'))
    assert result.status == 'success'
    publish(store, month=2, name='Replacement')
    entry, = list_report_history(store)
    assert entry.report_kind == 'adhoc'
    assert entry.datasets == (reference,)
    assert read_archived_report(store, result.report_id) == result.html


@pytest.mark.parametrize('selection', ['prior_only', 'reversed', 'duplicate', 'replacement', 'empty'])
def test_adhoc_references_must_be_ordered_pinned_subset_including_current(tmp_path, selection):
    from mobility.adhoc import AdhocResult

    store = DatasetStore(tmp_path)
    prior = publish(store, month=1)
    current = publish(store, month=2)
    report = generate_standard_dashboard(store, current.period)
    replacement = publish(store, month=2, name='Replacement')
    refs = {'prior_only': (prior,), 'reversed': (prior, current),
            'duplicate': (current, current), 'replacement': (replacement,), 'empty': ()}[selection]
    result = AdhocResult(status='success', message='Total trips', period=report.period,
                         report_id=report.report_id, datasets=refs, html='<html>Saved</html>')
    directory = tmp_path / 'reports' / report.report_id
    (directory / 'adhoc.json').write_text(result.model_dump_json())
    (directory / 'adhoc.html').write_text(result.html)
    with pytest.raises(ValueError, match='identity mismatch'):
        list_report_history(store)
