"""Verify structured claims against immutable tool evidence before rendering."""

from decimal import Decimal, ROUND_HALF_UP
from html import escape
from typing import Self

from pydantic import Field, model_validator

from mobility.contracts import Claim, Contract, EvidenceValue, ToolResult


class GroundingError(ValueError):
    """A draft refers to evidence that the current run did not produce."""


class ReportDraft(Contract):
    claims: tuple[Claim, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique_claim_ids(self) -> Self:
        if len({claim.claim_id for claim in self.claims}) != len(self.claims):
            raise ValueError('Claim IDs must be unique')
        return self


class VerifiedClaims(tuple):
    """Only the validator creates a collection accepted by the renderer."""

    def __new__(cls, claims: tuple[Claim, ...], *, _validated: bool = False):
        if not _validated:
            raise GroundingError('Claims must be validated before rendering')
        return super().__new__(cls, claims)


def _same_value(left: int | float | None, right: int | float | None) -> bool:
    return type(left) is type(right) and left == right


def _matches(claim: Claim, value: EvidenceValue) -> bool:
    fields = ('entity_id', 'metric_type', 'period', 'comparison_period', 'dimension',
              'category', 'unit', 'eligible', 'eligibility_reason')
    return all(getattr(claim, field) == getattr(value, field) for field in fields) and _same_value(
        claim.exact_tool_value, value.exact_tool_value)


def _arguments_match(claim: Claim, result: ToolResult) -> bool:
    args = result.arguments
    return (args.current_period is None or claim.period in {args.current_period, args.comparison_period}) and (
        args.comparison_period is None or args.comparison_period == claim.comparison_period
        or (result.tool_name in {'compare_periods', 'station_movers', 'analyze_station_variance'}
            and claim.period == args.comparison_period and claim.comparison_period is None)) and (
        args.station_id is None or args.station_id == claim.entity_id) and (
        args.dimension is None or args.dimension == claim.dimension)


def _datasets_match(claim: Claim, result: ToolResult) -> bool:
    if claim.datasets != result.datasets:
        return False
    periods = {dataset.period for dataset in result.datasets}
    return claim.period in periods and (claim.comparison_period is None or claim.comparison_period in periods)


def _transition_matches(claim: Claim) -> bool:
    if claim.transition == 'standalone':
        return True
    if (not claim.eligible or claim.comparison_period is None
            or claim.metric_type not in {'absolute_change', 'percentage_change'}):
        return False
    value = claim.exact_tool_value
    return ((claim.transition == 'increase' and value > 0)
            or (claim.transition == 'decrease' and value < 0)
            or (claim.transition == 'unchanged' and value == 0))


_METRIC_UNITS = {
    'trip_count': {'trips'}, 'current_volume': {'trips'},
    'share': {'percent'}, 'average_duration_minutes': {'minutes'},
    'absolute_change': {'trips', 'minutes', 'percentage_points'},
    'percentage_change': {'percent'}, 'contribution': {'percent'},
}


def _supported_claim(claim: Claim) -> bool:
    return (claim.unit in _METRIC_UNITS[claim.metric_type]
            and (claim.category is None or claim.dimension is not None)
            and (claim.metric_type != 'contribution' or (
                claim.category is not None and claim.dimension is not None
                and claim.comparison_period is not None)))


def validate_draft(draft: ReportDraft, evidence: tuple[ToolResult, ...], run_id: str) -> VerifiedClaims:
    """Atomically validate every claim; return nothing if one identity is wrong."""
    if not run_id:
        raise GroundingError('Run ID is required')
    by_call: dict[str, ToolResult] = {}
    for result in evidence:
        if result.run_id != run_id:
            continue
        if result.tool_call_id in by_call:
            raise GroundingError('Ambiguous tool call ID')
        by_call[result.tool_call_id] = result
    for claim in draft.claims:
        result = by_call.get(claim.tool_call_id)
        if (claim.run_id != run_id or result is None or result.status != 'success'
                or not _datasets_match(claim, result) or not _arguments_match(claim, result)
                or not _transition_matches(claim) or not _supported_claim(claim)
                or not any(_matches(claim, value) for value in result.values)):
            raise GroundingError(f'Claim {claim.claim_id} does not match successful evidence from this run')
        if claim.metric_type == 'contribution' and claim.eligible:
            same_dimension = tuple(value for value in result.values
                if value.metric_type == 'contribution' and value.eligible
                and value.entity_id == claim.entity_id and value.dimension == claim.dimension
                and value.period == claim.period and value.comparison_period == claim.comparison_period)
            highest = max(value.exact_tool_value for value in same_dimension)
            leaders = {value.category for value in same_dimension if value.exact_tool_value == highest}
            claimed = {item.category for item in draft.claims
                if item.tool_call_id == claim.tool_call_id and item.metric_type == 'contribution'
                and item.entity_id == claim.entity_id and item.dimension == claim.dimension
                and item.period == claim.period and item.comparison_period == claim.comparison_period}
            if claim.exact_tool_value != highest or claimed != leaders:
                raise GroundingError('Contribution claims must include every highest eligible category')
    return VerifiedClaims(draft.claims, _validated=True)


_TRANSITIONS = {
    'increase': 'Turning to an increase:',
    'decrease': 'Turning to a decrease:',
    'unchanged': 'Turning to a steady result:',
    'standalone': 'For this period:',
}

_METRICS = {
    'trip_count': 'trip count', 'share': 'share',
    'average_duration_minutes': 'average trip duration',
    'absolute_change': 'absolute change', 'percentage_change': 'percentage change',
    'contribution': 'contribution', 'current_volume': 'current volume',
}

_UNITS = {'trips': 'trips', 'percent': '%', 'minutes': 'minutes', 'percentage_points': 'percentage points'}


def _format_value(value: int | float) -> str:
    if isinstance(value, int):
        return f'{value:,}'
    rounded = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return f'{rounded:,.2f}'.rstrip('0').rstrip('.')


def render_verified_claims(claims: VerifiedClaims) -> str:
    """Render only validated data with fixed text and escaped identifiers."""
    if not isinstance(claims, VerifiedClaims):
        raise GroundingError('Claims must be validated before rendering')
    lines = []
    rendered_contributions = set()
    for claim in claims:
        if claim.metric_type == 'contribution' and claim.eligible:
            group = (claim.tool_call_id, claim.entity_id, claim.dimension, claim.period, claim.comparison_period)
            if group in rendered_contributions:
                continue
            rendered_contributions.add(group)
            from mobility.analytics import ContributionLeader, _wording
            leaders = tuple(ContributionLeader(category=item.category, contribution_pct=item.exact_tool_value)
                for item in claims if item.metric_type == 'contribution' and item.eligible
                and (item.tool_call_id, item.entity_id, item.dimension, item.period, item.comparison_period) == group)
            date = f'{claim.period.year:04d}-{claim.period.month:02d}'
            lines.append(f'<p>For {escape(claim.entity_id, quote=True)} {escape(claim.dimension.replace("_", " "), quote=True)} in {date}: {escape(_wording(leaders))}</p>')
            continue
        subject = escape(claim.entity_id, quote=True)
        if claim.dimension is not None:
            subject += f' ({escape(claim.dimension.replace("_", " "), quote=True)})'
        if claim.category is not None:
            subject += f', {escape(claim.category, quote=True)}'
        date = f'{claim.period.year:04d}-{claim.period.month:02d}'
        metric = _METRICS[claim.metric_type]
        if claim.eligible:
            value = _format_value(claim.exact_tool_value)
            statement = f'{subject} {metric} for {date}: {value} {_UNITS[claim.unit]}.'
            if claim.transition == 'decrease':
                statement = f'{subject} {metric} decreased by {_format_value(abs(claim.exact_tool_value))} {_UNITS[claim.unit]} for {date}.'
            elif claim.transition == 'increase':
                statement = f'{subject} {metric} increased by {_format_value(claim.exact_tool_value)} {_UNITS[claim.unit]} for {date}.'
            elif claim.transition == 'unchanged':
                statement = f'{subject} {metric} was unchanged for {date}.'
        else:
            statement = f'{subject} {metric} for {date} is unavailable.'
        lines.append(f'<p>{_TRANSITIONS[claim.transition]} {statement}</p>')
    return '\n'.join(lines)
