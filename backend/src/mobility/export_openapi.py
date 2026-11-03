"""Export API plus planned shared contracts without adding fake endpoints."""
import json
from pydantic.json_schema import models_json_schema
from .app import app
from .analytics import RankStationsResult
from .comparison import ComparisonResult, PythonBaseline, ComparisonStreamEvent
from .contracts import AnalysisRequest, Claim, DatasetReference, QualitySummary, RankStationsArgs, ToolResult


def export_schema() -> dict[str, object]:
    schema = app.openapi()
    _, definitions = models_json_schema(
        [(model, 'validation') for model in (AnalysisRequest, Claim, DatasetReference, QualitySummary, ToolResult, ComparisonResult, PythonBaseline, ComparisonStreamEvent, RankStationsArgs, RankStationsResult)],
        ref_template='#/components/schemas/{model}',
    )
    return {**schema, 'components': {'schemas': {
        **schema.get('components', {}).get('schemas', {}), **definitions['$defs'],
    }}}


if __name__ == '__main__':
    print(json.dumps(export_schema(), indent=2, sort_keys=True))
