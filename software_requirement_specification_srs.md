# Software Requirements Specification: Agentic Monthly Mobility Reporting Workflow

## 1. Purpose and Requirements Authority

Build a web-based workflow to ingest Jersey City Citi Bike monthly trip data, calculate reproducible metrics, investigate station declines, and produce static HTML reports.

This SRS consolidates the original requirements, subsequent user decisions, and peer feedback. It supersedes the original alternatives: Streamlit, monthly-only analytical storage, regex matching of narrative numbers, harmonic mean duration, and in-place dataset replacement.

The LLM routes requests, plans approved tool use, inspects aggregate results, chooses follow-up calculations, and selects structured claims. Python performs all calculations, enforces rules and budgets, validates evidence, and renders factual sentences. Raw CSV rows must never enter LLM prompts or LLM-facing errors.

Deliverables include a deterministic baseline, adaptive agent workflow, evaluation cases curated by all three team members, and a demo showing an actual follow-up decision. Production readiness requires verification, not just an architectural label. Section 14 identifies information not supplied; implementation must not silently invent it.

## 2. Technology Stack

| Component | Required technology |
| --- | --- |
| Frontend | Next.js / React with Tailwind CSS |
| Backend | Python / FastAPI |
| Deterministic processing | Pandas |
| Cleaned trip storage | Persistent local Raw Lake; immutable CSV or Parquet versions |
| Monthly KPI storage | SQLite, versioned with its corresponding trip dataset |
| Active dataset registry | Master SQLite configuration table; transactional activation |
| LLM | OpenAI `gpt-5-nano` through Portkey |
| Contracts | Strict Pydantic inputs and outputs |
| Reports | Archived static HTML with PNG/SVG assets and template-rendered narrative |

SQLite supplies pre-calculated top-level monthly metrics. Daily trends, station rankings, and fresh breakdowns query the cleaned Raw Lake using Pandas. Cloud storage is outside the currently agreed scope.

## 3. Dataset Scope and Ingestion

### 3.1. File identity and scope

- Accept one or two uploaded raw CSVs or ZIPs containing CSVs. An upload may include two months; group files by filename-defined month and validate each month separately. Each archive must contain data for one month.
- Canonical monthly filename: `JC-YYYYMM-citibike-tripdata.csv`.
- The filename defines the month. Scope is determined by the approved JC filename convention; no additional geographic filtering was requested.
- Concatenate every CSV in a ZIP before monthly cleaning and aggregation. Validate each CSV, not only the first archive member.
- Archive members must belong to the same filename-defined month. Timestamp spillover follows the tolerance below, which supersedes the earlier blanket multi-month timestamp rejection.
- The selected study, evaluation, and demo months are **January 2026 (`2026-01`) and February 2026 (`2026-02`)**. January is the prior month and February is the current month for the primary comparison. August 2026 is not part of this selected dataset; finding a local August file does not change project scope.
- Source URLs, actual archive/member names, checksums, counts, and any multipart naming variants require the manifest in Section 14. Canonical expected CSV names are `JC-202601-citibike-tripdata.csv` and `JC-202602-citibike-tripdata.csv`; verified source packaging is recorded in the Phase 0 manifest. Accept `JC-YYYYMM-citibike-tripdata.zip` and `JC-YYYYMM-citibike-tripdata.csv.zip`; process uploaded files and CSV members alphabetically, preserving row order and ignoring macOS metadata. Other multipart naming variants remain unapproved.
- A rejected upload must not change the active month, even when replacing existing data.

### 3.2. Schema

Validate the 13 canonical fields in every CSV:

`ride_id`, `rideable_type`, `started_at`, `ended_at`, `start_station_name`, `start_station_id`, `end_station_name`, `end_station_id`, `start_lat`, `start_lng`, `end_lat`, `end_lng`, `member_casual`.

Preserve station IDs as identifiers, not numerical measurements.

### 3.3. Mandatory cleaning sequence

Apply these stages to the concatenated upload in order. Exclusion counts must not count a removed row again at a later stage.

1. **Invalid timestamps:** Drop rows with invalid or null timestamps. Use `America/New_York` for month boundaries.
2. **Month validation:** Denominator = rows remaining after timestamp exclusions. Calculate the percentage whose `started_at` falls outside the filename month. If **> 1.0%**, reject and quarantine the entire upload. If **<= 1.0%**, drop those rows and proceed. Exactly 1.0% is accepted. Reject a zero-row denominator.
3. **Deduplication:** Deduplicate exact `ride_id` strings across the entire upload. Keep the first occurrence, dropping subsequent occurrences. Establish a stable archive-member processing order in the manifest so “first” is reproducible.
4. **Missing stations:** A row fails if either station ID is null, blank, or NaN. Denominator = rows remaining after month filtering and deduplication. If affected rows are **>= 5.0%**, reject and quarantine the entire upload. Otherwise drop only those rows. Exactly 5.0% is rejected.
5. **Duration:** Calculate trip duration from timestamps. Drop trips **< 60 seconds** or **> 86,400 seconds**. Both boundary values remain valid.
6. **Categories:** Map unexpected membership and fleet values to `Unknown`. Keep those rows in totals and share denominators. Record source-value mappings in the dataset dictionary.
7. **Final empty check:** Reject the entire upload if zero valid rows remain.

Apply thresholds without first rounding percentages. Rejected ingestion leaves the prior active dataset and KPI records unchanged.

### 3.4. Quality accounting and reconciliation

Persist `quality_summary`: source filenames, per-CSV parsed counts, total parsed rows, each sequential exclusion count, final valid trips, category normalization counts, threshold denominators, and rejection reason where applicable. Unknown normalization retains rows; it is not an exclusion.

Verify for every accepted upload:

- Sum of per-CSV parsed counts = concatenated parsed count.
- Parsed rows minus non-overlapping exclusion counts = final valid rows.
- Final valid rows = Raw Lake row count = SQLite Total Trips.
- Summed daily starts = summed station starts = Total Trips.
- Counts within each category dimension, including Unknown, sum to Total Trips.

Preserve quality evidence for rejected uploads. These checks reconcile all supplied CSVs; they do not prove that an incomplete source file covers an entire calendar month.

## 4. Storage, Versioning, and Replacement

### 4.1. Two-tier architecture

Each immutable monthly version contains:

1. **Raw Lake:** Persistent cleaned CSV/Parquet trip data, read-only after creation. Historical detail remains available after application restart.
2. **KPI store:** A corresponding SQLite file with pre-calculated monthly totals, category counts/shares including Unknown, arithmetic average duration, and version/quality metadata.

KPI records identify period, dataset version, Total Trips, Member/Casual/Unknown shares, Classic/E-bike/Unknown shares, and Average Trip Duration. Retain count evidence sufficient to reproduce shares and comparisons.

### 4.2. Activation and recovery

- A corrected upload creates a new isolated directory and SQLite file, such as `jc_2026_02_v2`; never modify the active version in place.
- Finish cleaning, reconciliation, validation, and persistent artifact writes before activation.
- A master configuration table maps each month to its active version. A single transactional update activates that month's new version.
- Both tiers resolve through the same version ID. Do not maintain independently updated active pointers.
- A crash before activation leaves the old version active. A committed activation must reference a complete, queryable version. Incomplete orphan versions must never become active.
- A report run records and consistently uses its current/prior dataset versions; a concurrent replacement must not mix versions within a run.
- Keep old static HTML reports archived, together with their assets and source version metadata. Do not regenerate them automatically after replacement.

## 5. Deterministic Analytical Rules

### 5.1. Metrics

All metrics use final cleaned trip starts. Station volume is starts at `start_station_id`, not starts plus arrivals.

| Metric | Definition |
| --- | --- |
| Total Trips | Final cleaned trip count |
| Member/Casual/Unknown Share | Category starts / total valid starts for the selected entity x 100 |
| Classic/E-bike/Unknown Share | Category starts / total valid starts for the selected entity x 100 |
| Average Trip Duration (minutes) | Arithmetic mean of valid durations in seconds / 60 |
| Absolute change | Current volume - prior volume |
| Percentage change | (Current volume - prior volume) / prior volume x 100, only when eligible |

Unknown remains in each dimension's denominator and is explicitly displayed. Unrounded category shares sum to 100% within each dimension. Display rounding must not change stored evidence.

### 5.2. Eligibility and materiality

- Comparisons use adjacent calendar months `T` and `T-1`, including year boundaries.
- A station or segment needs **at least 100 valid prior-month trips** for percentage-based materiality and contribution calculations.
- Use the station's own prior count for station eligibility and each segment's own prior count for segment contribution eligibility. This comparison threshold does not suppress single-month descriptive shares.
- Zero prior station volume means `new`; zero current station volume means `removed`. Both are excluded from station percentage-change logic and remain eligible for absolute rankings. Removed is an explicit exclusion even when its prior sample is sufficient.
- Small prior samples do not exclude stations from absolute rankings. Undefined/ineligible percentages are null, never zero.
- Materiality uses the **absolute percentage change**: `< 5%` = `Flat`; `5% <= x <= 10%` = `Moderate Change`; `> 10%` = `Significant Change`. Determine direction separately from the signed delta.

### 5.3. Rankings and adaptive trigger

`station_movers` evaluates all stations and returns:

- `top_5_increases`: positive absolute changes, largest first.
- `top_5_decreases`: negative changes ranked by absolute drop, largest first.
- `mandatory_investigation_candidate`: the eligible station with the largest absolute drop satisfying **decline > 10% AND absolute drop > 100 rides**, or null.

Select the candidate from all stations, not just the display rankings. Break station ties by `station_id` alphanumerically ascending. New/removed stations remain eligible for absolute rankings. Removed stations do not trigger mandatory investigation. Investigate only one mandatory candidate per run.

### 5.4. Contribution calculations and language

`analyze_station_variance` returns independent `member_casual` and `rideable_type` breakdowns with category labels, current/prior counts, deltas, eligibility, and contributions.

Contribution percentage = `100 x (segment_current_volume - segment_prior_volume) / (total_current_volume - total_prior_volume)`.

The total is the same station's starts, including Unknown. Membership and fleet are separate overlapping dimensions; do not add their contributions. Identify the highest contributing category independently in each dimension, including its identity and value (`member_contribution_pct` and `bike_type_contribution_pct`).

If total change is exactly zero, return null and suppress the contribution sentence. Ineligible values also cannot produce contribution claims. For eligible values, Python applies these mutually exclusive templates:

| Contribution | Wording |
| --- | --- |
| `> 100%` | “More than accounted for by [Segment].” |
| `== 100%` | “Driven entirely by [Segment].” |
| `80% <= x < 100%` | “Primarily driven by [Segment].” |
| `< 80%` | “Driven by a mix of factors.” |

If Unknown is the highest contributor, replace standard wording with exactly: **“Driven primarily by unclassified data.”** Null contribution still suppresses the sentence. For equally highest eligible contributions, display all tied categories; explicitly label an unclassified contribution when Unknown ties. The exact tied-category template and claim representation must be finalized before affected implementation; do not arbitrarily select a winner. The single-winner wording above applies when there is one eligible leader.

These statements describe mathematical decompositions. Do not claim causes such as weather, closures, or operational changes.

## 6. Supported Requests and Missing Periods

A strict `RequestIntent` routes to Standard Report, Supported Ad-Hoc, or Refusal.

Supported ad-hoc requests:

1. Single-month **Total Trips, Member/Casual Share, Classic/E-bike Share, or Average Trip Duration**; include Unknown when showing share breakdowns.
2. Specific-station performance for a month, or comparisons with its immediately preceding month, using approved metrics and station tools.
3. A visual breakdown of a supported query using `make_chart`.

Forecasts, causal explanations, non-adjacent comparisons, multi-month trends, and metrics outside the catalog return `ERR_UNSUPPORTED_INTENT`, an explanation, and a supported alternative.

Call `get_available_periods` before producing `AnalysisPlan`. Retrieve available months and active versions; the backend plan gate verifies tool existence, supported scope, and required data.

- Standard report with prior month: comparative path.
- Standard report without prior month: standalone path plus a backend-generated note that MoM comparisons are unavailable.
- Explicit ad-hoc comparison without its prior month: `ERR_UNSUPPORTED_INTENT`; explain missing data and offer an alternative. Do not request an upload mid-run.

Missing comparison data must not make a standard report crash.

## 7. UI and Standard Dashboard

### 7.1. Interface

Provide drag-and-drop upload, a command/chat input, live progress, an HTML report viewer, quality messages, and visible limitation/error notices.

Visible stages:

1. Data Ingest.
2. Agent Planning.
3. Tool Execution, with a special adaptive-follow-up indicator.
4. Final Report Generation.

Grounding is internal to final generation. Never show unvalidated LLM content. Expose initial station aggregates, the chosen follow-up and arguments, tool status, and validated results; do not expose raw trip rows or private model reasoning.

### 7.2. Deterministic baseline

`generate_standard_dashboard` runs in Python before the reasoning loop and costs **zero agent tool calls**. It queries SQLite for scorecards and the Raw Lake for detailed charts/rankings.

The five required report sections are:

1. **KPI Scorecard:** Total Trips, Average Trip Duration (minutes), fleet mix, and rider mix, including Unknown.
2. **Daily Trend:** Daily start counts; standalone line or current/prior dual-line comparison.
3. **Mix Breakdowns:** Membership and fleet bars, including Unknown.
4. **Top Stations / Movers:** Standalone top five stations by starts; comparative top five increases and top five decreases, with eligibility labels.
5. **Data-Quality Summary:** Source coverage, exact exclusions, final valid trips, and Unknown counts.

These are five sections, not five separate LLM chart calls. Save static HTML and its PNG/SVG assets so archives remain readable after replacement. The baseline is also the fixed evaluation comparator and failure fallback.

## 8. Workflow and Tool Contracts

### 8.1. Execution

1. Ingest an upload when supplied; validate, reconcile, and activate its immutable version.
2. Generate the deterministic baseline for the selected reporting month outside the loop.
3. Route the request. Obtain available periods before planning; retrieve static scope/definitions as needed.
4. Produce and validate the bounded `AnalysisPlan`.
5. Execute initial tools. Comparative reporting inspects `station_movers` before final claims.
6. The LLM inspects initial aggregates and selects the required variance investigation when a candidate exists.
7. Validate follow-up execution and draft claims against the run's evidence.
8. Render the approved claims/transitions, or return baseline-only partial output.

Adaptive behavior is the post-result tool decision and decomposition. The LLM cannot invent calculations, modify thresholds, or override stopping rules.

### 8.2. Operations

All operations require strict Pydantic input/output schemas. Internal helpers are not separately exposed LLM tools unless explicitly approved.

| Operation | Inputs and responsibility | Output/source |
| --- | --- | --- |
| `validate_and_load_file` | Upload reference; pipeline only | Period, quality evidence, activated version or rejection |
| `generate_standard_dashboard` | Period, pinned versions; pipeline only | Deterministic HTML/assets and baseline evidence |
| `get_available_periods` | Available-data lookup | Months and active versions; required before plan |
| `retrieve_context` | Approved query | Static rules, definitions, scope, templates |
| `kpi_summary` | Period | Exact SQLite monthly metrics |
| `compare_periods` | Current and adjacent prior periods | KPI changes, units, eligibility, materiality |
| `daily_trend` | Period | Daily Raw Lake start counts; baseline helper |
| `station_analysis` | Period, top_n | Standalone Raw Lake starts ranking |
| `station_movers` | Current and adjacent prior periods | Two rankings and global investigation candidate |
| `analyze_station_variance` | station_id, current_period, comparison_period | Both breakdown dimensions and contribution evidence |
| `make_chart` | Approved chart type and validated query/result reference | Ad-hoc asset and provenance; one in-loop call |

`station_movers_tool` in earlier discussion means `station_movers`. The old ambiguous station direction parameter is superseded by starts-only analysis. Tools must not expose arbitrary file paths or arbitrary generated code execution.

### 8.3. Follow-up validation

When a candidate exists, the trace must contain a subsequent `analyze_station_variance` call with all of:

- `status == success`.
- `arguments.station_id == candidate_id`.
- `arguments.current_period == reporting_period`.
- `arguments.comparison_period == prior_month`.
- Successfully returned data for both `rideable_type` and `member_casual`, with eligibility/null metadata where applicable.

A failed call, wrong station/period, or missing dimension does not satisfy the requirement. Failure consumes the result-validation gate's one retry and requires replanning within remaining budgets.

## 9. Claims, Provenance, and Grounding

`ReportDraft` contains strict `Claim` objects and hardcoded transition-enum selections. No free-form factual prose or transition text is permitted.

Each claim carries:

- `tool_call_id`, referencing successful evidence from this run.
- `entity_id`, a stable station or aggregate/segment identity.
- `metric_type`, distinguishing current volume, absolute change, percentage change, share, duration, contribution, etc.
- `period` and applicable `comparison_period`.
- `exact_tool_value`, unrounded.
- Dimension/category and other parameters needed to distinguish the output.

Evidence records include run ID, arguments, status, dataset versions, canonical output values, units, and eligibility. Baseline pipeline results also receive evidence IDs; referencing them does not require redundant in-loop calls.

Grounding checks the complete composite identity against the exact output logged for this run. Reject wrong months, comparison months, stations, metrics, categories, units, values, stale versions, failed executions, and other-run evidence. Finding the same number elsewhere is insufficient.

Python renders names, dates, direction, units, rounded values, materiality, and contribution wording from verified data and hardcoded templates. Transitions must be enum selections, for example “Turning to station performance:”. Unknown templates/fields and unsupported claims are rejected.

Exact values must match canonical tool values; the LLM cannot derive new numbers. Apply rounding only during rendering, never for grounding or threshold decisions. This approach supersedes regex checking and placeholder-based narrative generation.

A grounding failure triggers `ERR_UNGROUNDED_CLAIM` and one bounded gate retry. Never display failed draft content.

## 10. Budgets, Retries, and Failure Modes

- Maximum **10 LLM-selected tool invocations** per run, including failures and retries. In-loop planning/context tools count.
- Maximum **6 LLM API calls** per run, including routing, planning, replanning, claim selection, and retries.
- Maximum **one retry per named gate per run**, not per visit.
- Ingestion, Python validation, baseline generation, and HTML skeleton creation outside the loop cost zero agent calls.
- Missing-follow-up retry uses the validation retry and one LLM call to replan. Subsequent selected tools consume normal calls.
- Python checks budgets before dispatch. Retrying cannot reset or exceed them.

| Failure | Behavior |
| --- | --- |
| Invalid ingestion | Reject/quarantine; preserve active data; show quality details |
| Unsupported intent/missing requested comparison | Refuse with reason and supported alternative |
| Reasoning budget exhausted | Baseline only: “Pass with limitations: Reasoning budget exhausted. Displaying standard baseline metrics only.” |
| Grounding/result validation fails after retry | Baseline only: “Pass with limitations: Narrative validation failed. Displaying standard baseline metrics only.” |
| Tool failure | Log/count the call; allow only bounded retries; reject its output as evidence |

Partial reports contain **no LLM-generated or LLM-selected narrative**. “Pass with limitations” means baseline availability, not agent success. Failed ingestion with no active valid dataset cannot produce a new baseline.

Persist run status, counters, trace, artifacts, and errors: `ERR_SCHEMA_MISMATCH`, `ERR_UNSUPPORTED_INTENT`, `ERR_TOOL_EXECUTION`, `ERR_UNGROUNDED_CLAIM`, `ERR_BUDGET_EXCEEDED`. Include stage-specific result-validation reasons.

## 11. Baseline Evaluation and Acceptance

Compare the agent against a fixed deterministic KPI workflow using the **same dataset versions, cleaning rules, metric implementations, and chart tools**. The fixed workflow produces the baseline without LLM-selected investigations/narrative. Differences must reflect orchestration rather than different formulas or data.

Measure numerical correctness, claim attribution, required follow-up completion, additional verified decomposition, refusals/fallbacks, tool/LLM calls, elapsed time, and available model usage/cost. Check expected results independently; plausible language is not evidence.

All **three team members** curate challenging cases. Each case records its author, dataset/version, request, expected route, expected figures/claims, expected sequence, and completion/failure state.

Required cases:

- Correct value attached to the wrong month, station, metric, or comparison period.
- Forged evidence IDs, stale versions, other-run evidence, and unsupported claims.
- Exactly 1.0% versus greater than 1.0% out-of-month rows.
- Just below versus exactly 5.0% missing stations using the correct denominator.
- Invalid timestamps, zero cleaned rows, and duration boundaries.
- Cross-CSV duplicates and per-file/monthly reconciliation.
- Exactly 100 versus fewer than 100 prior trips; new/removed stations.
- Exactly 10% or exactly 100 rides versus greater-than-both trigger cases.
- A qualifying candidate outside the displayed five decreases.
- Equal station changes and station-ID tie-breaking.
- Contribution boundaries, zero total change, and Unknown dominance.
- Missing prior month: standalone report versus explicit-comparison refusal.
- Non-adjacent, multi-month, causal, forecasting, and unsupported-metric requests.
- Failed, wrong-period, wrong-station, or incomplete follow-up; retries/budget exhaustion.
- Interrupted replacement before/after activation and preserved archived reports.

Use unit tests for formulas/boundaries, integration tests for storage and orchestration, and E2E tests for upload/report, visible follow-up, refusal, and baseline-only fallback. Project testing target: at least 80% coverage. Acceptance requires verified expected results and demonstrated failure behavior.

## 12. Demo Scenario

Using January 2026 as the prior month and February 2026 as the newly uploaded reporting month:

1. Show the fixed baseline using the same data/tools.
2. Upload the new month; show all archive members accounted for, exclusions, and activation.
3. Request the comparative report or ask about a station decline.
4. Show initial station results and candidate selection.
5. Show the agent's subsequent variance call, station/periods, and both breakdowns.
6. Show validated figures and final template-rendered report.
7. Demonstrate rejection of a deliberately wrong-month claim and its bounded correction or fallback.

Use a real qualifying decline or clearly label a separate synthetic evaluation fixture. Do not silently alter real data to manufacture a demo.

## 13. Implementation Safeguards

Validate uploads, archive contents, requests, and tool contracts. Treat station names as data rather than executable HTML; restrict archive extraction to its intended directory. Keep credentials outside source and visible traces. Maintain provenance from source manifest through dataset version, KPI record, execution, claim, and archived report.

The LLM must not execute arbitrary generated code. Authentication, capacity, resource limits, retention, and recovery operations require the decisions below before claiming production readiness.

## 14. Explicit Pending Project Inputs

Phase 0 records live in [the dataset manifest](docs/phase-0/dataset-manifest.md), [decision register](docs/decisions.md), and [acceptance checklist](docs/phase-0/acceptance-checklist.md). The following subsequent user decisions resolve portions of the pending inputs below:

- Accept one or two uploaded files; ignore macOS archive metadata. One upload may span two months, each validated separately.
- Use the public Citi Bike S3 bucket as a downloadable source, not as application storage.
- Map `member`/`casual` to Member/Casual and `classic_bike`/`electric_bike` to Classic/E-bike; other values become Unknown.
- Display up to two decimal places without rounding stored evidence. Align charts by day number, leaving absent days as gaps rather than zeros.
- Users supply a month; no omitted-month default is approved. Ask users to select among ambiguous station matches. Each request supplies its month and any required station; retain no analytical chat context.
- Target a hosted application with retention of at most six months. Hosting/access controls, resource limits beyond file count, retention clock, and artifact coverage remain pending.
- The three evaluation curators are Abhee and Monisha (analytics), and Ashutosh (ingestion and agent behavior). Individual analytics case allocation, and authored fixtures remain pending.

Agreed behavioral rules are specified above. These remaining project inputs were not supplied and must not be silently assumed:

| Pending input | Required resolution |
| --- | --- |
| Source files for confirmed months | Source URLs, packaging, checksums, and parsed counts verified in the manifest; cleaned totals and the real demo candidate are cross-checked in [checked results](docs/phase-0/cleaned-expectations.md); curator review remains pending |
| Multipart naming | Canonical CSV and both verified ZIP formats approved with alphabetical processing; other multipart variants remain unapproved |
| Category dictionary | Mapping approved above; observed source values and counts verified in the Phase 0 manifest |
| Contribution ties | Joint display approved, explicitly labeling Unknown; exact tied-category templates and claim representation remain pending |
| Display formatting | Up to two decimals; day-number alignment with gaps for absent days approved |
| Request context | Explicit month, station selection for ambiguous matches, and no retained analytical context approved; no omitted-month default |
| Evaluation ownership | Three named curators, fixtures, expected results, and final acceptance evidence |
| Deployment/operations | Hosting, authentication/isolation, concurrency, upload/expansion limits, latency/cost targets, backup, retention, version cleanup |

Resolve these before implementing the affected behavior or declaring full production readiness.
