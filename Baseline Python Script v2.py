"""Simple analytical comparator over the agent's pinned, cleaned January/February data.

Run with the backend Python environment; see docs/phase-7.md for an example.
This shares cleaning/storage readers, but independently calculates totals/rankings.
"""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from time import perf_counter
from typing import Any, Iterator


sys.path.insert(0, str(Path(__file__).resolve().parent / 'backend' / 'src'))
from mobility.baseline import BaselineReport
from mobility.contracts import DatasetReference
from mobility.storage import DatasetStore
from mobility.python_baseline import calculate


class ReadOnlyStore(DatasetStore):
    """Reuse identity/hash/expiry checks without creating or updating storage."""

    def __init__(self, root: Path) -> None:
        if root.is_symlink() or not root.is_dir():
            raise ValueError('Data root must be an existing real directory')
        self.root = root.resolve()
        self.registry = self.root / 'registry.sqlite'
        if self.registry.is_symlink() or not self.registry.is_file():
            raise ValueError('Data root must contain an existing registry.sqlite')

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.registry.as_uri() + '?mode=ro', uri=True)) as db:
            yield db

    def _resolve(self, reference: DatasetReference) -> Path:
        directory = self.root / 'versions' / reference.version_id
        for path in (self.root / 'versions', directory,
                     directory / 'cleaned.csv', directory / 'metadata.json'):
            if path.is_symlink():
                raise ValueError('Dataset paths must not be symlinks')
        return super()._resolve(reference)


def write_workbook(result: dict[str, Any], destination: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Winter Summary'
    sheet.append(['Jersey City Winter 2026 — Fixed Python Baseline'])
    sheet['A1'].font = Font(name='Calibri', size=16, bold=True, color='1F4E78')
    sheet.append(['Pinned cleaned data; monthly totals and combined station starts only'])
    sheet.append(['Monthly valid-trip totals'])
    sheet.append(['Month', 'Total Rides'])
    for month, count in result['monthly_totals'].items():
        sheet.append([month, count])
    sheet.append([])
    sheet.append(['Top 5 Start Stations (January + February Combined)'])
    sheet.append(['Rank', 'Station ID', 'Station Name', 'Total Rides'])
    for rank, station in enumerate(result['top_stations'], start=1):
        sheet.append([rank, station['station_id'], station['station_name'], station['ride_count']])
        # Station identifiers/names are untrusted labels, never Excel formulas.
        for column in (2, 3):
            sheet.cell(sheet.max_row, column).data_type = 's'
    for row in (4, 9):
        for cell in sheet[row]:
            cell.font = Font(name='Calibri', bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='1F4E78')
            cell.alignment = Alignment(horizontal='center')
    for row in sheet.iter_rows(min_row=5):
        for cell in row:
            if isinstance(cell.value, int):
                cell.number_format = '#,##0'
    chart = BarChart()
    chart.type = 'col'
    chart.style = 10
    chart.title = 'January vs. February Valid Trips'
    chart.y_axis.title = 'Valid trips'
    chart.x_axis.title = 'Month'
    chart.add_data(Reference(sheet, min_col=2, min_row=4, max_row=6), titles_from_data=True)
    chart.set_categories(Reference(sheet, min_col=1, min_row=5, max_row=6))
    chart.legend = None
    sheet.add_chart(chart, 'F4')
    for column in sheet.columns:
        width = max(len(str(cell.value or '')) for cell in column)
        sheet.column_dimensions[get_column_letter(column[0].column)].width = min(max(width + 3, 12), 65)
    workbook.save(destination)
    workbook.close()


def run(data_root: Path, snapshot: Path, output_dir: Path) -> dict[str, Any]:
    started = perf_counter()
    store = ReadOnlyStore(data_root)
    if output_dir.resolve().is_relative_to(store.root):
        raise ValueError('Output directory must be outside the working data root')
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError('Output directory must be new; existing files will not be overwritten')
    report = BaselineReport.model_validate_json(snapshot.read_text())
    result = calculate(store, report)
    calculation_seconds = perf_counter() - started
    # Check the optional Excel dependency before creating an output directory.
    import openpyxl  # noqa: F401

    output_dir.mkdir(parents=True, exist_ok=False)
    workbook_started = perf_counter()
    write_workbook(result, output_dir / 'Citi_Bike_Winter_2026_Basic_Report.xlsx')
    record = result | {
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'snapshot_report_id': report.report_id,
        'datasets': [ref.model_dump(mode='json') for ref in report.datasets],
        'scope': 'Shared pinned cleaned inputs; independent monthly totals and combined station ranking. Not independent cleaning validation or the full five-section SRS dashboard.',
        'ranking': 'January plus February starts; descending count, ascending station ID; latest nonblank display name',
        'llm_calls': 0, 'selected_agent_tool_calls': 0,
        'timing_seconds': {'read_validate_and_calculate': calculation_seconds,
                           'excel_export': perf_counter() - workbook_started},
    }
    (output_dir / 'baseline.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--snapshot', required=True, type=Path, help='Existing February baseline evidence.json pinning both months')
    parser.add_argument('--output-dir', required=True, type=Path, help='New directory outside the working data root')
    args = parser.parse_args()
    try:
        record = run(args.data_root, args.snapshot, args.output_dir)
    except (ValueError, KeyError, OSError, sqlite3.Error, ImportError) as error:
        parser.exit(1, f'Baseline failed: {error}\n')
    print(json.dumps({'output': str(args.output_dir), 'monthly_totals': record['monthly_totals'],
                      'top_stations': record['top_stations'], 'timing_seconds': record['timing_seconds']}))


if __name__ == '__main__':
    main()
