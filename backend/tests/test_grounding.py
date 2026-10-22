import pytest
from pydantic import ValidationError

from mobility.contracts import Claim, DatasetReference, EvidenceValue, Period, ToolArguments, ToolResult
from mobility.grounding import GroundingError, ReportDraft, render_verified_claims, validate_draft


PERIOD = Period(year=2026, month=2)
PRIOR = Period(year=2026, month=1)
CURRENT = DatasetReference(period=PERIOD, version_id='current', sha256='a' * 64)
PREVIOUS = DatasetReference(period=PRIOR, version_id='previous', sha256='b' * 64)


def evidence_value(**changes):
    fields = dict(entity_id='HB106', metric_type='absolute_change', period=PERIOD,
                  comparison_period=PRIOR, dimension=None, category=None, unit='trips',
                  exact_tool_value=-718, eligible=True, eligibility_reason=None)
    return EvidenceValue(**(fields | changes))


def result(**changes):
    fields = dict(run_id='run-1', tool_call_id='call-1', stage='execution',
                  tool_name='station_movers', status='success',
                  arguments=ToolArguments(current_period=PERIOD, comparison_period=PRIOR),
                  datasets=(CURRENT, PREVIOUS), values=(evidence_value(),))
    return ToolResult(**(fields | changes))


def claim(**changes):
    fields = evidence_value().model_dump() | dict(claim_id='claim-1', tool_call_id='call-1',
                                                   run_id='run-1', datasets=(CURRENT, PREVIOUS),
                                                   transition='decrease')
    return Claim(**(fields | changes))


def test_valid_claim_renders_only_verified_fixed_template():
    verified = validate_draft(ReportDraft(claims=(claim(),)), (result(),), 'run-1')
    assert verified == (claim(),)
    html = render_verified_claims(verified)
    assert 'HB106' in html and '718' in html and 'decreased' in html
    assert 'call-1' not in html


@pytest.mark.parametrize('change', [
    {'entity_id': 'OTHER'}, {'metric_type': 'trip_count'},
    {'period': PRIOR}, {'comparison_period': None}, {'dimension': 'rideable_type'},
    {'category': 'Member'}, {'unit': 'minutes'}, {'exact_tool_value': -717},
    {'eligible': False, 'exact_tool_value': None, 'eligibility_reason': 'low_sample'},
    {'tool_call_id': 'forged'}, {'run_id': 'other'},
    {'datasets': (DatasetReference(period=PERIOD, version_id='stale', sha256='a' * 64), PREVIOUS)},
])
def test_rejects_composite_identity_mismatch(change):
    with pytest.raises(GroundingError):
        validate_draft(ReportDraft(claims=(claim(**change),)), (result(),), 'run-1')


def test_rejects_failed_or_other_run_evidence_and_never_returns_partial_claims():
    good = claim()
    forged = claim(claim_id='second', exact_tool_value=99)
    for bad_result in (result(status='failed'), result(run_id='other')):
        with pytest.raises(GroundingError):
            validate_draft(ReportDraft(claims=(good, forged)), (bad_result,), 'run-1')
    with pytest.raises(GroundingError):
        validate_draft(ReportDraft(claims=(good, forged)), (result(),), 'run-1')


def test_rejects_value_inconsistent_with_tool_arguments():
    wrong_station = result(arguments=ToolArguments(current_period=PERIOD, comparison_period=PRIOR, station_id='OTHER'))
    with pytest.raises(GroundingError):
        validate_draft(ReportDraft(claims=(claim(),)), (wrong_station,), 'run-1')


def test_rejects_transition_that_contradicts_verified_change():
    with pytest.raises(GroundingError):
        validate_draft(ReportDraft(claims=(claim(transition='increase'),)), (result(),), 'run-1')


def test_rejects_unsupported_metric_unit_even_if_evidence_contains_it():
    bad = claim(metric_type='share', unit='minutes', comparison_period=None, transition='standalone')
    tool = result(arguments=ToolArguments(current_period=PERIOD),
                  values=(evidence_value(metric_type='share', unit='minutes', comparison_period=None),))
    with pytest.raises(GroundingError):
        validate_draft(ReportDraft(claims=(bad,)), (tool,), 'run-1')


def test_strict_draft_rejects_prose_unknown_transition_and_bool_number():
    with pytest.raises(ValidationError):
        ReportDraft.model_validate({'claims': [], 'prose': 'Made up'})
    with pytest.raises(ValidationError):
        claim(transition='invented')
    with pytest.raises(ValidationError):
        claim(exact_tool_value=True)


def test_renderer_escapes_identifiers_and_uses_up_to_two_decimals():
    item = claim(entity_id='<script>x</script>', exact_tool_value=12.345, unit='minutes',
                 metric_type='average_duration_minutes', comparison_period=None, transition='standalone')
    verified = validate_draft(ReportDraft(claims=(item,)),
                              (result(arguments=ToolArguments(current_period=PERIOD),
                                      values=(evidence_value(entity_id='<script>x</script>',
                                                              exact_tool_value=12.345, unit='minutes',
                                                              metric_type='average_duration_minutes', comparison_period=None),)),),
                              'run-1')
    html = render_verified_claims(verified)
    assert '&lt;script&gt;' in html and '<script>' not in html
    assert '12.35' in html and '12.345' not in html


def test_comparison_tool_can_ground_prior_month_value():
    prior_value = evidence_value(entity_id='month', metric_type='trip_count', period=PRIOR,
                                 comparison_period=None, exact_tool_value=1584)
    tool = result(tool_name='compare_periods', values=(prior_value,))
    prior_claim = claim(entity_id='month', metric_type='trip_count', period=PRIOR,
                        comparison_period=None, exact_tool_value=1584, transition='standalone')
    assert validate_draft(ReportDraft(claims=(prior_claim,)), (tool,), 'run-1') == (prior_claim,)


def test_tied_contributions_require_all_leaders_and_render_joint_wording():
    member = evidence_value(metric_type='contribution', dimension='member_casual', category='Member',
                            exact_tool_value=50.0, unit='percent')
    unknown = evidence_value(metric_type='contribution', dimension='member_casual', category='Unknown',
                             exact_tool_value=50.0, unit='percent')
    tool = result(tool_name='analyze_station_variance',
                  arguments=ToolArguments(current_period=PERIOD, comparison_period=PRIOR, station_id='HB106'),
                  values=(member, unknown))
    member_claim = claim(metric_type='contribution', dimension='member_casual', category='Member',
                         exact_tool_value=50.0, unit='percent', transition='standalone')
    unknown_claim = claim(claim_id='claim-2', metric_type='contribution', dimension='member_casual',
                          category='Unknown', exact_tool_value=50.0, unit='percent', transition='standalone')
    with pytest.raises(GroundingError):
        validate_draft(ReportDraft(claims=(member_claim,)), (tool,), 'run-1')
    verified = validate_draft(ReportDraft(claims=(member_claim, unknown_claim)), (tool,), 'run-1')
    html = render_verified_claims(verified)
    assert 'Jointly led by Member, Unknown (unclassified) (each 50%).' in html
    assert html.count('Jointly led by') == 1
