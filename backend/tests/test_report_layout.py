"""Shared report presentation must preserve text and exact, eligible values."""
import pytest

from mobility.report_layout import kpi_card, kpi_grid, panel, panel_grid, report_document, segment_panel


def test_shared_cards_escape_labels_values_and_notes():
    card = kpi_card('<Station>', '8 < 10', 'Sample < 100')
    html = report_document('Report <title>', kpi_grid([card]) + panel_grid([panel('Exact <values>', '<p>Verified</p>')]))
    assert '<title>Report &lt;title&gt;</title>' in html
    assert 'class="report-kpis"' in html
    assert 'class="report-card"' in html
    assert '&lt;Station&gt;' in html and '8 &lt; 10' in html and 'Sample &lt; 100' in html
    assert 'Exact &lt;values&gt;' in html and '<p>Verified</p>' in html
    assert 'name="viewport"' in html and '@media' in html


def test_segment_bars_use_supplied_shares_and_keep_unavailable_values_visible():
    html = segment_panel('Rider type', [('Member', '75 trips · 75%', 75), ('Unknown <category>', 'Unavailable', None)])
    assert 'width:75.000%' in html
    assert 'Unknown &lt;category&gt;' in html and 'Unavailable' in html
    assert html.count('class="report-bar"') == 1


@pytest.mark.parametrize('share', [-1, 101, float('nan'), float('inf')])
def test_segment_bars_reject_invalid_percentage(share):
    with pytest.raises(ValueError):
        segment_panel('Mix', [('Member', 'Untrusted percentage', share)])
