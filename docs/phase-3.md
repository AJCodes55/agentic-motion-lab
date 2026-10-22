# Phase 3 — Deterministic Analytics and Fixed Baseline

Status: complete for local deterministic reporting, 2026-10-18. Phase 2 changes remain local and uncommitted.

## Scope

Use immutable dataset references from Phase 2. SQLite supplies monthly KPIs; Pandas reads the cleaned Raw Lake for daily starts, stations and variance. The deterministic dashboard uses no LLM calls and remains the fixed comparator for later agent evaluation.

The five sections are KPI Scorecard, Daily Trend, Mix Breakdowns, Top Stations / Movers, and Data-Quality Summary. Missing prior-month data produces a standalone baseline with an explicit comparison limitation. Reports preserve HTML, SVG assets, exact evidence and version references after dataset replacement.

D17 resolves contribution ties: all eligible leaders remain structured entries; render “Jointly led by [categories] (each [value]%).” Unknown is labeled “Unknown (unclassified)” in this sentence. Single-leader templates and null suppression follow the SRS.

## Verification

| Check | Result |
| --- | --- |
| Backend unit/integration | 103 passed; 95.91% statement coverage |
| Analytics / baseline coverage | 100% / 98% |
| Frontend unit/integration | 35 passed; 100% lines, 98.57% statements, 90.47% branches |
| Browser tests | 3 passed; upload, replacement, rejected correction and baseline generation included |
| Frontend lint, typecheck, production build | Passed; shared contracts regenerated and final typecheck passed |
| Code, Python, React and security review | No remaining critical/high findings; initial evidence, eligibility and display issues corrected |
| Real data | 39,198 January / 25,387 February valid starts; all independent daily totals match, including a zero-start February 23 |
| Mandatory candidate | HB106, River St & Newark St: 1,584 to 866 starts, delta -718 (-45.33% displayed) |
| Variance | Both category dimensions match independently checked counts and contributions |

[Aggregate verification evidence](phase-3-real-data.json) records real results without trip rows. Verification used temporary storage; those dataset/archive files were removed afterward. The evidence is an aggregate test record, not a retained demo database.

Boundary checks include prior samples 99/100, new/removed stations, strict trigger thresholds, a candidate outside the displayed five, station-ID ties, contribution wording/Unknown/ties/null cases, year boundaries, adjacent periods, and calendar gaps. Existing Phase 2 checks remain green.

## Usage

1. Start the backend and frontend using the existing [local setup](phase-1.md). Restart an older backend process to load the new report route.
2. Upload accepted data or fetch the explicitly selected month.
3. Select the reporting month and press **Generate baseline report**.

`POST /reports` accepts `{"period":{"year":2026,"month":2}}`. It returns the safe API envelope containing a strict `BaselineReport`: report ID, period, pinned datasets, self-contained HTML, typed evidence, and `llm_calls: 0`. Missing current data returns a safe 404. Missing prior data produces a standalone report.

Archives live under `MOBILITY_DATA_ROOT/reports/<report_id>/`: `index.html`, `evidence.json`, and SVG assets. The browser displays the report in a sandboxed iframe. Archives survive corrected-upload activation. History browsing remains Phase 5.

The baseline records canonical counts, shares, duration, daily starts, comparison deltas, and displayed station/candidate values with run and version identities. It does not automatically investigate station variance; later agent work selects that follow-up. The variance operation itself is implemented and tested.

## Limits

No LLM integration or hosted deployment is included. Agent planning, validated claim selection and grounding remain Phase 4. Hosting, authentication/isolation, retention and operational recovery decisions remain pending. Existing user preview processes were preserved; verification ran on isolated ports. No commit or push was performed.
