# Phase 5 — Supported Ad-Hoc Features

Status: implemented and locally verified. GitHub publication was authorized on 2026-10-22; publication progress is tracked in [the summary](summary.md).

## Supported behavior

The supported-query form requires an explicit reporting month and offers Total Trips, Member/Casual Share, Classic/E-bike Share, Average Trip Duration, and station starts. Share tables include Unknown. The four aggregate metric families are single-month requests. Station starts can compare with the immediately preceding calendar month, using the existing sample-eligibility, new/removed, and both variance-dimension rules. The command input routes through strict typed extraction into the same service. Unsupported forecasts, causal requests, metrics, non-adjacent comparisons, multi-month scope, and unavailable requested comparisons are refused with a supported alternative.

Station lookup checks IDs and names in the pinned reporting snapshot. Exact matches take priority over partial matches; multiple IDs require a visible selection. Selecting a station submits the complete month/query again. Neither interface sends analytical chat history. A selected month that conflicts with an explicitly extracted command month is refused.

Calculations, station lookup, tables and optional fixed SVG charts share the baseline's immutable snapshot. Charts receive successful same-run evidence and carry the same values as the answer. No generated chart code or filesystem paths are accepted. HTML, exact evidence and chart assets are saved under the baseline report ID, with the ad-hoc manifest published last and partial artifacts removed on a failed write.

History shows one final report per run, preferring ad-hoc, then agent, then baseline. Saved baseline evidence and HTML remain on disk. Access reads archived HTML rather than recalculating current datasets, checks pinned identities and saved HTML, and rejects invalid IDs, traversal and symlinks. The report viewer remains sandboxed.

## Local use

1. Start the frontend and backend using the existing setup instructions.
2. Upload accepted monthly data and select a reporting month.
3. Choose a supported metric, add a station for station starts, and optionally request comparison or a chart.
4. Resolve any station choices explicitly, then use “Refresh report history” to open the saved result.

API additions: `POST /adhoc`, `GET /reports/history`, and `GET /reports/history/{report_id}`, with fixed-origin Next.js proxies and regenerated shared contracts.

## Verification

- Backend: 201 tests passed, 94.48% coverage. New tests cover every metric family, independently expected mixed-category figures, Unknown shares, ambiguity, single-station results outside top-five rankings, adjacent comparisons, missing prior data, refusals, command-period conflicts, long IDs, pinned replacements, chart identity, archive rollback and archive path/integrity checks.
- Frontend: 64 tests passed; 95.93% statement, 84.69% branch, 94.25% function and 98.73% line coverage. Typecheck and lint passed. The production build succeeded during browser startup.
- Python, React/TypeScript, general code and security reviews completed. Findings about single-month archive subsets, conflicting command months, station input bounds and unsupported comparison controls were fixed.
- Browser: all six tests passed on isolated ports, including a real upload → ambiguous station selection → verified table/chart → exact archived report flow. The two new workflows also passed three repeated runs each (6/6). Tracing identified stale Chromium mouse targeting when scrolling past the sandboxed iframe. Explicit scroll and hover before the ordinary history click synchronized the test; no forced click, generated click, fixed sleep or application workaround was added. Test servers stopped after verification.

- Pre-publication dependency audit: updated the reproducible `certifi` pin from 2026.10.18 to 2026.10.19 after the audit flagged PYSEC-2026-4320. The maintainer identifies 10.18 as patched; 10.19 restores unaffected roots and clears the audit. Python audit now reports no known vulnerabilities (the local application package is not listed on PyPI). Production npm audit reports zero vulnerabilities; the existing development-only braces advisory remains documented in [Phase 1](phase-1.md). Backend regression tests were rerun after the patch.

## Limits

Natural-language classification remains model-dependent; structured supported queries avoid provider calls. New routing tests use injected models rather than a new live university-gateway request. Hosting, authentication, retention, recovery, concurrency, and cancellation remain Phase 6 decisions and work. No production-readiness claim is made.
