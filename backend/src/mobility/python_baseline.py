"""Independent comparator shared by the v2 CLI and comparison UI; no Excel dependency."""
from typing import Any
import pandas as pd
from mobility.baseline import BaselineReport
from mobility.contracts import Period
from mobility.storage import DatasetStore


def calculate(store: DatasetStore, report: BaselineReport) -> dict[str, Any]:
    """Count starts directly with Pandas; never call production KPI/analytics helpers."""
    periods = {Period(year=2026, month=month) for month in (1, 2)}
    if (report.period != Period(year=2026, month=2) or len(report.datasets) != 2
            or {ref.period for ref in report.datasets} != periods):
        raise ValueError('Snapshot must pin both January and February 2026 for a February report')
    totals, inputs, frames = {}, [], []
    for reference in sorted(report.datasets, key=lambda ref: ref.period.month):
        metadata = store.read_metadata(reference)
        frame = store.read_frame(reference)
        if frame.empty or len(frame) != metadata['quality']['valid_rows']:
            raise ValueError('Cleaned input must be nonempty and reconcile with its quality record')
        if frame['start_station_id'].str.strip().eq('').any():
            raise ValueError('Cleaned input contains a missing station ID')
        key = f'{reference.period.year}-{reference.period.month:02d}'
        totals[key] = len(frame)
        inputs.append({'dataset': reference.model_dump(mode='json'),
                       'quality': metadata['quality'], 'sources': metadata.get('sources', [])})
        frames.append(frame[['start_station_id', 'start_station_name']])
    combined = pd.concat(frames, ignore_index=True)
    counts = combined.groupby('start_station_id').size().rename('ride_count').reset_index()
    ranked = counts.sort_values(['ride_count', 'start_station_id'], ascending=[False, True]).head(5)
    # Prefer the latest nonblank display label; IDs alone determine identity and ties.
    names = combined.loc[combined.start_station_name.str.strip().ne('')].drop_duplicates(
        'start_station_id', keep='last').set_index('start_station_id').start_station_name.to_dict()
    stations = [{'station_id': row.start_station_id,
                 'station_name': names.get(row.start_station_id, row.start_station_id),
                 'ride_count': int(row.ride_count)} for row in ranked.itertuples(index=False)]
    return {'monthly_totals': totals, 'top_stations': stations, 'inputs': inputs}


