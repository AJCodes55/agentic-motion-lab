"""Same-snapshot Python and bounded agent comparison with attributed evidence."""
from collections.abc import Callable
import json
import os
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field

from mobility.agent import AgentRun, AgentService
from mobility.baseline import BaselineReport, generate_standard_dashboard
from mobility.contracts import Contract, DatasetReference, Period, ToolResult
from mobility.python_baseline import calculate
from mobility.storage import DatasetStore

JAN = Period(year=2026, month=1)
FEB = Period(year=2026, month=2)


class ComparisonRequest(Contract):
    period: Period


class BaselineStation(Contract):
    station_id: str
    station_name: str
    ride_count: int = Field(ge=0)


class BaselineInput(Contract):
    dataset: DatasetReference
    quality: dict[str, Any]
    sources: list[dict[str, Any]]


class PythonBaseline(Contract):
    monthly_totals: dict[str, int]
    top_stations: tuple[BaselineStation, ...]
    inputs: tuple[BaselineInput, ...]


class ComparisonRow(Contract):
    month: str
    python_total: int = Field(ge=0)
    agent_total: int | None = Field(ge=0)
    difference: int | None
    status: Literal['match', 'mismatch', 'unavailable']


class ComparisonTiming(Contract):
    shared_preparation: float = Field(ge=0, allow_inf_nan=False)
    python_calculation: float = Field(ge=0, allow_inf_nan=False)
    agent_workflow: float = Field(ge=0, allow_inf_nan=False)


class ComparisonResult(Contract):
    report_id: str
    period: Period
    datasets: tuple[DatasetReference, ...]
    baseline: PythonBaseline
    agent: AgentRun
    rows: tuple[ComparisonRow, ...]
    timing_seconds: ComparisonTiming
    dollar_cost: None = None


class BaselineReadyTiming(Contract):
    shared_preparation: float = Field(ge=0, allow_inf_nan=False)
    python_calculation: float = Field(ge=0, allow_inf_nan=False)


class ComparisonBaselineEvent(Contract):
    type: Literal['baseline']
    data: PythonBaseline
    report_id: str
    datasets: tuple[DatasetReference, ...]
    timing_seconds: BaselineReadyTiming


class ComparisonResultEvent(Contract):
    type: Literal['result']
    data: ComparisonResult


class ComparisonErrorEvent(Contract):
    type: Literal['error']
    message: str


class ComparisonStageEvent(Contract):
    type: Literal['stage']
    name: Literal['Data Ingest', 'Agent Planning', 'Tool Execution', 'Final Report Generation']
    status: Literal['complete', 'failed', 'skipped']


class ComparisonToolEvent(Contract):
    type: Literal['tool']
    data: ToolResult


class ComparisonCandidateEvent(Contract):
    type: Literal['candidate']
    candidate_id: str


class ComparisonStreamEvent(Contract):
    event: ComparisonBaselineEvent | ComparisonResultEvent | ComparisonErrorEvent | ComparisonStageEvent | ComparisonToolEvent | ComparisonCandidateEvent = Field(discriminator='type')


def _archive_path(store: DatasetStore, report_id: str, *parts: str) -> Path:
    if not re.fullmatch(r'[a-f0-9]{32}', report_id):
        raise ValueError('Invalid report ID')
    path = store.root / 'reports' / report_id
    ancestors = [store.root, store.root / 'reports', path]
    for part in parts:
        path = path / part
        ancestors.append(path)
    if any(item.is_symlink() for item in ancestors):
        raise ValueError('Unsafe archive path')
    return path


def validate_snapshot(store: DatasetStore, snapshot: BaselineReport, period: Period, *, fixed_demo: bool = False) -> None:
    """Validate the committed snapshot and original versions without repinning active data."""
    if snapshot.period != period or not snapshot.datasets or snapshot.datasets[0].period != period:
        raise ValueError('Snapshot reporting period mismatch')
    if fixed_demo and (period != FEB or tuple(ref.period for ref in snapshot.datasets) != (FEB, JAN)):
        raise ValueError('Demo requires accepted January and February 2026 datasets')
    saved = BaselineReport.model_validate_json(_archive_path(store, snapshot.report_id, 'evidence.json').read_text())
    if saved != snapshot or _archive_path(store, snapshot.report_id, 'index.html').read_text() != snapshot.html:
        raise ValueError('Snapshot differs from committed report')
    if len({ref.period for ref in snapshot.datasets}) != len(snapshot.datasets):
        raise ValueError('Duplicate snapshot period')
    for reference in snapshot.datasets:
        store.read_metadata(reference)
        store.read_frame(reference)


def comparison_rows(baseline: PythonBaseline, agent: AgentRun, report_id: str,
                    datasets: tuple[DatasetReference, ...]) -> tuple[ComparisonRow, ...]:
    """Use only unambiguous successful selected-tool evidence; never narrative or baseline KPIs."""
    counts: dict[str, list[int]] = {month: [] for month in baseline.monthly_totals}
    ids = [item.tool_call_id for item in agent.trace]
    if agent.run_id == report_id and agent.period == FEB and agent.datasets == datasets:
        for index, item in enumerate(agent.trace, start=1):
            if (item.stage != 'execution' or item.status != 'success' or item.tool_name != 'compare_periods'
                    or item.run_id != report_id or item.datasets != datasets
                    or item.tool_call_id != f'{report_id}_selected_{index}'
                    or index > agent.counters.tool_calls or index > 10
                    or ids.count(item.tool_call_id) != 1
                    or item.arguments.current_period != FEB or item.arguments.comparison_period != JAN
                    or item.arguments.station_id is not None or item.arguments.top_n is not None
                    or item.arguments.dimension is not None):
                continue
            for value in item.values:
                month = f'{value.period.year:04d}-{value.period.month:02d}'
                if (month in counts and value.entity_id == 'month' and value.metric_type == 'trip_count'
                        and value.unit == 'trips' and value.eligible and value.dimension is None
                        and value.category is None and value.comparison_period is None
                        and type(value.exact_tool_value) is int and value.exact_tool_value >= 0):
                    counts[month].append(value.exact_tool_value)
    rows = []
    for month, expected in sorted(baseline.monthly_totals.items()):
        found = counts[month]
        actual = found[0] if len(found) == 1 else None
        difference = actual - expected if actual is not None else None
        rows.append(ComparisonRow(month=month, python_total=expected, agent_total=actual,
            difference=difference, status='unavailable' if actual is None else 'match' if difference == 0 else 'mismatch'))
    return tuple(rows)


def validate_archive(store: DatasetStore, report_id: str) -> ComparisonResult:
    result = ComparisonResult.model_validate_json(_archive_path(store, report_id, 'comparison.json').read_text())
    snapshot = BaselineReport.model_validate_json(_archive_path(store, report_id, 'evidence.json').read_text())
    validate_snapshot(store, snapshot, FEB, fixed_demo=True)
    run = AgentRun.model_validate_json(_archive_path(store, report_id, 'agent', 'agent-run.json').read_text())
    if (result.report_id != report_id or result.period != FEB or result.datasets != snapshot.datasets
            or run != result.agent or (run.report_html and _archive_path(store, report_id, 'agent', 'index.html').read_text() != run.report_html)
            or run.run_id != report_id or run.period != FEB or run.datasets != snapshot.datasets
            or result.baseline != PythonBaseline.model_validate_json(json.dumps(calculate(store, snapshot)))
            or result.rows != comparison_rows(result.baseline, run, report_id, snapshot.datasets)):
        raise ValueError('Comparison archive identity or evidence mismatch')
    return result


def _persist(store: DatasetStore, result: ComparisonResult) -> None:
    directory = _archive_path(store, result.report_id)
    linked = AgentRun.model_validate_json(_archive_path(store, result.report_id, 'agent', 'agent-run.json').read_text())
    if (linked != result.agent or linked.run_id != result.report_id or linked.period != result.period
            or linked.datasets != result.datasets):
        raise ValueError('Comparison requires matching committed agent evidence')
    destination = directory / 'comparison.json'
    if destination.exists() or destination.is_symlink():
        raise ValueError('Comparison already archived')
    staging = directory / f'.comparison-{uuid4().hex}.tmp'
    try:
        with staging.open('x', encoding='utf-8') as handle:
            handle.write(result.model_dump_json(indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        staging.rename(destination)
        store._sync_directory(directory)
    finally:
        staging.unlink(missing_ok=True)


class ComparisonService:
    def __init__(self, store: DatasetStore, model) -> None:
        self.store = store
        self.model = model

    def run(self, period: Period, progress: Callable[[dict], None] | None = None) -> ComparisonResult:
        if period != FEB:
            raise ValueError('Select February 2026 for the fixed January/February demo')
        started = perf_counter()
        if not {JAN, FEB} <= {item.period for item in self.store.list_active()}:
            raise KeyError('Both January and February 2026 must be accepted before this demo')
        snapshot = generate_standard_dashboard(self.store, period)
        validate_snapshot(self.store, snapshot, period, fixed_demo=True)
        preparation = perf_counter() - started
        started = perf_counter()
        baseline = PythonBaseline.model_validate_json(json.dumps(calculate(self.store, snapshot)))
        calculation = perf_counter() - started
        if progress:
            progress({'type': 'baseline', 'data': baseline.model_dump(mode='json'),
                      'report_id': snapshot.report_id,
                      'datasets': [ref.model_dump(mode='json') for ref in snapshot.datasets],
                      'timing_seconds': {'shared_preparation': preparation, 'python_calculation': calculation}})
        started = perf_counter()
        agent = AgentService(self.store, self.model).run(period, 'Compare January and February 2026 monthly totals and investigate any qualifying station decline in the standard February report',
            progress=progress, snapshot=snapshot, comparison_mode=True)
        elapsed = perf_counter() - started
        result = ComparisonResult(report_id=snapshot.report_id, period=period, datasets=snapshot.datasets,
            baseline=baseline, agent=agent, rows=comparison_rows(baseline, agent, snapshot.report_id, snapshot.datasets),
            timing_seconds=ComparisonTiming(shared_preparation=preparation, python_calculation=calculation,
                                            agent_workflow=elapsed))
        _persist(self.store, result)
        return result
