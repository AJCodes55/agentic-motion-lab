"""Read-only access to committed reports and their pinned dataset references."""
from pathlib import Path
import re
from typing import Literal

from mobility.adhoc import AdhocResult
from mobility.agent import AgentRun
from mobility.baseline import BaselineReport
from mobility.contracts import Contract, DatasetReference, Period
from mobility.storage import DatasetStore


class ReportHistoryEntry(Contract):
    report_id: str
    period: Period
    datasets: tuple[DatasetReference, ...]
    report_kind: Literal['baseline', 'agent', 'adhoc']
    status: Literal['complete', 'partial', 'refused']


def _safe_path(root: Path, *parts: str) -> Path:
    path = root.joinpath(*parts)
    descendants = (root, *(root.joinpath(*parts[:index]) for index in range(1, len(parts) + 1)))
    if any(candidate.is_symlink() for candidate in descendants):
        raise ValueError('Unsafe archive path')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Unsafe archive path')
    return path


def _load(store: DatasetStore, report_id: str):
    if not re.fullmatch(r'[a-f0-9]{32}', report_id):
        raise ValueError('Invalid report ID')
    root = store.root / 'reports'
    directory = _safe_path(root, report_id)
    baseline_path = _safe_path(root, report_id, 'evidence.json')
    if not baseline_path.is_file():
        raise KeyError('Archived report not found')
    baseline = BaselineReport.model_validate_json(baseline_path.read_text(encoding='utf-8'))
    if baseline.report_id != report_id:
        raise ValueError('Archived report identity mismatch')
    adhoc_path = _safe_path(root, report_id, 'adhoc.json')
    if adhoc_path.is_file():
        result = AdhocResult.model_validate_json(adhoc_path.read_text(encoding='utf-8'))
        if (result.report_id != report_id or result.period != baseline.period
                or not result.datasets or result.datasets[0] != baseline.datasets[0]
                or result.datasets != tuple(ref for ref in baseline.datasets if ref in result.datasets)
                or result.status != 'success'):
            raise ValueError('Archived report identity mismatch')
        return ReportHistoryEntry(report_id=report_id, period=result.period, datasets=result.datasets,
                                  report_kind='adhoc', status='complete'), result.html, _safe_path(root, report_id, 'adhoc.html')
    agent_path = _safe_path(root, report_id, 'agent', 'agent-run.json')
    if agent_path.is_file():
        run = AgentRun.model_validate_json(agent_path.read_text(encoding='utf-8'))
        if run.run_id != report_id or run.period != baseline.period or run.datasets != baseline.datasets:
            raise ValueError('Archived report identity mismatch')
        if run.report_html:
            return ReportHistoryEntry(report_id=report_id, period=run.period, datasets=run.datasets,
                                      report_kind='agent', status=run.status), run.report_html, _safe_path(root, report_id, 'agent', 'index.html')
    return ReportHistoryEntry(report_id=report_id, period=baseline.period, datasets=baseline.datasets,
                              report_kind='baseline', status='complete'), baseline.html, _safe_path(root, report_id, 'index.html')


def list_report_history(store: DatasetStore) -> tuple[ReportHistoryEntry, ...]:
    """List committed reports in stable ID order without touching active datasets."""
    root = store.root / 'reports'
    if not root.exists():
        return ()
    _safe_path(root)
    entries = []
    for directory in sorted(root.iterdir(), key=lambda path: path.name, reverse=True):
        if not re.fullmatch(r'[a-f0-9]{32}', directory.name):
            continue
        if directory.is_symlink():
            continue
        try:
            entry, _, _ = _load(store, directory.name)
        except KeyError:
            continue
        entries.append(entry)
    return tuple(entries)


def read_archived_report(store: DatasetStore, report_id: str) -> str:
    """Read the saved HTML, never regenerate it against corrected datasets."""
    _, expected_html, path = _load(store, report_id)
    html = path.read_text(encoding='utf-8')
    if html != expected_html:
        raise ValueError('Archived HTML does not match its saved evidence')
    return html
