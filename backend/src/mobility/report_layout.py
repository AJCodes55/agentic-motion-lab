"""Shared, self-contained report presentation; calculations stay in their services.

Text arguments are escaped here. HTML content arguments accept only markup
already generated and escaped by the application's deterministic renderers.
"""
from collections.abc import Iterable
from html import escape
from math import isfinite


_SEGMENT_COLOR = {
    'Member': '#1d4e89', 'Casual': '#5c7a6e', 'Classic': '#3d5a4c',
    'E-bike': '#6b5b7a', 'Unknown': '#8d8279', 'Unknown (unclassified)': '#8d8279',
}


def kpi_card(label: str, value: str, note: str = '', tone: str = '') -> str:
    detail = f'<span class="report-note">{escape(str(note))}</span>' if note else ''
    classes = 'report-card decline' if tone == 'decline' else 'report-card'
    return (f'<div class="{classes}"><span>{escape(str(label))}</span>'
            f'<strong>{escape(str(value))}</strong>{detail}</div>')


def kpi_grid(cards: Iterable[str]) -> str:
    return '<div class="report-kpis">' + ''.join(cards) + '</div>'


def panel(title: str, content: str) -> str:
    return f'<div class="report-panel"><h2>{escape(title)}</h2>{content}</div>'


def panel_grid(panels: Iterable[str]) -> str:
    return '<div class="report-panels">' + ''.join(panels) + '</div>'


def dashboard(lead: str, cards: Iterable[str], panels: Iterable[str] = (), footnote: str = '') -> str:
    """Station-comparison shell: context line, KPI cards, then breakdown panels."""
    parts = [f'<p class="meta">{escape(lead)}</p>', kpi_grid(cards)]
    rendered = tuple(panels)
    if rendered:
        parts.append(panel_grid(rendered))
    if footnote:
        parts.append(f'<p class="report-note">{escape(footnote)}</p>')
    return '<div class="station-dash">' + ''.join(parts) + '</div>'


def segment_panel(title: str, rows: Iterable[tuple], note: str = '') -> str:
    items = []
    for row in rows:
        label, value, share = row[0], row[1], row[2]
        detail = row[3] if len(row) > 3 and row[3] else ''
        bar = ''
        if share is not None:
            if not isfinite(share) or not 0 <= share <= 100:
                raise ValueError('Report bar shares must be finite percentages between 0 and 100')
            color = _SEGMENT_COLOR.get(str(label), '#24588e')
            bar = (f'<div class="report-bar" role="img" aria-label="{escape(str(label))} {escape(str(value))}">'
                   f'<span style="width:{share:.3f}%;background:{color}"></span></div>')
        detail_html = f'<span class="meta">{escape(str(detail))}</span>' if detail else ''
        items.append(
            f'<li class="report-segment seg"><div class="report-segment-label seg-top">'
            f'<span class="seg-name">{escape(str(label))}</span><span>{escape(str(value))}</span></div>'
            f'{bar}{detail_html}</li>')
    description = f'<p class="report-note meta">{escape(note)}</p>' if note else ''
    return panel(title, description + '<ul class="report-segments">' + ''.join(items) + '</ul>')


_STYLES = """
body{font:16px/1.6 system-ui;max-width:1100px;margin:1rem auto;padding:1rem;color:#172a36;background:#fdfdfe}
main{min-width:0;display:grid;gap:1.25rem}
h1{font-size:clamp(1.5rem,4vw,2rem);line-height:1.25;overflow-wrap:anywhere;margin:0 0 .5rem}
h2{font-size:1.25rem;line-height:1.35;margin:0 0 1rem}h3,h4{line-height:1.4}
section{margin:0;min-width:0}p{overflow-wrap:anywhere}
.report-kpis,.station-dash .kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem}
.report-kpis:has(>:nth-child(2):last-child),.station-dash .kpis:has(>:nth-child(2):last-child){grid-template-columns:repeat(2,minmax(0,1fr))}
.report-kpis>:last-child:nth-child(3n+1),.station-dash .kpis>:last-child:nth-child(3n+1){grid-column:1 / -1}
.report-card,.report-panel,.station-dash .kpi,.station-dash .panel{min-width:0;border:1px solid #dce6f0;border-radius:8px;padding:1rem;background:#fff}
.report-card>span,.station-dash .kpi span,.station-dash .meta{display:block;color:#425563;font-size:.95rem}
.report-card strong,.station-dash .kpi strong{display:block;font-size:1.75rem;line-height:1.2;overflow-wrap:anywhere;margin:.2rem 0}
.report-panels,.station-dash .panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}
.report-panels>:last-child:nth-child(odd),.station-dash .panels>:last-child:nth-child(odd){grid-column:1 / -1}
.report-panel>*:last-child{margin-bottom:0}
.report-segments,.station-dash ul{list-style:none;margin:0;padding:0}
.report-segment,.station-dash .seg{display:grid;gap:.35rem;margin-top:1rem}
.report-segment-label,.station-dash .seg-top{display:flex;justify-content:space-between;gap:1rem}
.report-bar,.station-dash .bar{height:.7rem;background:#eef3f5;border-radius:999px;overflow:hidden}
.report-bar span{display:block;height:100%;background:#24588e}
.station-dash .bar span{display:block;height:100%}
.station-dash{display:grid;gap:1.25rem}.kpi.decline strong,.station-dash .decline strong{color:#9f1239}
table{border-collapse:collapse;width:max-content;min-width:100%}
th,td{border:1px solid #ccd4da;padding:.65rem .85rem;text-align:left;vertical-align:top;white-space:nowrap}
th{background:#eef3f5}tbody tr:nth-child(even){background:#f7fafb}
.table-scroll,.chart-scroll{overflow-x:auto;margin:1rem 0;max-width:100%;min-width:0}
:focus-visible{outline:3px solid #155e75;outline-offset:3px}
svg{display:block;width:100%;min-width:670px;height:auto;font:14px system-ui}
.report-note{color:#425563;font-size:.95rem}
@media(max-width:700px){.report-kpis,.report-panels,.station-dash .kpis,.station-dash .panels{grid-template-columns:1fr}}
@media(max-width:600px){body{margin:0;padding:.75rem}th,td{padding:.5rem}.report-segment-label{flex-wrap:wrap;gap:.25rem}}
@media print{body{max-width:none;margin:0}.table-scroll,.chart-scroll{overflow:visible}table{width:100%;min-width:0}th,td{white-space:normal}svg{min-width:0}.report-panel,.report-card{break-inside:avoid}}
"""


def report_document(title: str, body: str) -> str:
    """Wrap trusted, already escaped report HTML without external dependencies."""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(title)}</title><style>{_STYLES}</style></head><body>'
            f'<main id="report-content" class="report-dashboard"><h1>{escape(title)}</h1>{body}</main></body></html>')
