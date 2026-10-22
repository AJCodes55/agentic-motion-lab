# Project Decisions

Last updated: 2026-10-19.

This is the canonical project-wide decision record. Update it after every crucial decision. Record what changed, why, approval/source, affected phase, and unresolved details. Preserve superseded decisions explicitly; do not silently replace them. The [SRS](../software_requirement_specification_srs.md) remains the requirements authority. Update affected requirements and the [live summary](summary.md) when a decision changes behavior or scope.

## Approved Product Decisions

All entries below were confirmed by the user on 2026-10-18. D01–D08 preserve the IDs from the original Phase 0 register.

| ID | Decision | Reason or source | Scope and remaining details |
| --- | --- | --- | --- |
| D01 | Accept one or two uploaded files, including two different months. Group and validate each month separately. Accept canonical `JC-YYYYMM-citibike-tripdata.csv` and both verified ZIP suffixes (`.zip` and `.csv.zip` after `tripdata`). Process uploaded files and CSV members alphabetically, preserving row order. Ignore macOS metadata. | User clarified file count and approved all recommendations; source packaging verified. | Phase 2. Other multipart naming variants remain unapproved. Cross-month behavior is resolved by D16: independent acceptance, not a batch-wide transaction. |
| D02 | Display all equally highest eligible contributing categories; explicitly label unclassified contributions when Unknown ties. Never arbitrarily choose one or sum overlapping dimensions. | User approved joint representation. | Phase 3/4. Exact wording and structured leaders resolved under D17. |
| D03 | Align daily charts by day number; missing days in the shorter month are gaps, never zero. | User approved recommendation for unequal month lengths. | Phase 3. January has 31 days; February 2026 has 28. |
| D04 | Require an explicit reporting month and any station needed for station-specific requests. Ask users to select among ambiguous station matches. Retain no analytical chat context. | User confirmed month provision and approved request-context recommendation. | Phases 1, 4–5. Aggregate reports require no station; no omitted-month default is approved. |
| D05 | Keep Phase 0 records in `docs/phase-0/`. Use `docs/summary.md` for live progress and `docs/decisions.md` for crucial project decisions. | User approved documentation location, then requested ongoing summary and decision files. | All phases. Update summary after every phase/important step and decisions after every crucial decision. |
| D06 | Abhee and Monisha own analytics evaluation. Ashutosh owns ingestion and agent behavior evaluation. | Explicit named assignments supersede the earlier proposed user/colleague role allocation. | Individual analytics case split remains pending. All three still contribute challenging cases; approval is not evidence of individual authorship. |
| D07 | Target a hosted application. | User confirmed eventual hosting. | Provider, authentication/isolation, hosted concurrency/byte/expansion limits, latency/cost targets, backup and recovery remain pending. Local Phase 2 limits are approved under D15. |
| D08 | Retain data for at most six months. | User specified maximum retention. | Retention clock and coverage of sources, versions, traces, reports and evidence remain pending; reconcile expiry with archive requirements before implementation. |
| D09 | Use January 2026 as prior and February 2026 as current for study, evaluation and primary demo; exclude the local August file. | User's revised plan and SRS. | Verified sources and counts are in the [manifest](phase-0/dataset-manifest.md). |
| D10 | Fetch requested source data from the public Citi Bike S3 bucket. | User identified the public source. | Source download only; application cloud storage remains outside approved scope. |
| D11 | Map `member`/`casual` to Member/Casual and `classic_bike`/`electric_bike` to Classic/E-bike; other values become Unknown. | User confirmed mappings. | Preserve Unknown in totals and denominators; exact source values/counts recorded in the manifest. |
| D12 | Render values with up to two decimal places; retain unrounded evidence. | User specified display precision; SRS requires exact grounding/thresholds. | Applies to analytics, charts, reports and claims. |
| D13 | Approve all 44 boundary case specifications. | User explicitly stated that everything was reviewed and approved. | Supersedes initial I01–I03-only approval. Application execution and individual curator contributions are separate work. See [review record](phase-0/boundary-review-cases.md). |
| D14 | Publish application source, tests, CI, locks, contracts and current documentation to `AJCodes55/agentic-motion-lab`; exclude downloadable raw datasets, superseded planning/conversation files, local assistant/editor configuration, secrets, dependencies and generated build/cache files. Keep `.env.example` and generated shared API types. | User explicitly approved the proposed exclusion list before publication. | Initial publish contains 42 files, under 0.5 MB. [Ignore rules](../.gitignore) enforce the exclusions. |
| D15 | For Phase 2 local development: 25 MB per file, 50 MB total file bytes per request, 200 MB expanded CSV data, at most 100 CSV members, and one ingestion at a time. | User explicitly approved the proposed local limits before implementation. | Decimal MB (1,000,000 bytes). Hosted limits remain subject to operational review. Multipart transport overhead is bounded separately from file content. |
| D16 | A two-month upload may activate a valid month while rejecting an invalid month. Each month remains internally transactional. | User chose “Accept valid month; reject invalid month.” | Supersedes the unresolved cross-month behavior under D01; no all-or-nothing transaction across months. |
| D17 | Display tied contribution leaders as “Jointly led by [categories] (each [value]%).” Label Unknown as “Unknown (unclassified)”; preserve all tied leaders as structured category/value entries. | User explicitly approved wording and structure when starting Phase 3. | Phases 3–4. Existing single-winner templates and null suppression remain unchanged. |
| D18 | Use the university-provided OpenAI API key directly for Phase 4, replacing the SRS Portkey gateway requirement. | User explicitly requested “switch Phase 4 to direct OpenAI” on 2026-10-19. | Superseded by D19 when the user supplied the university gateway URL and model slug. The backend-only key and grounding requirements remain. |
| D19 | Use the university-provided OpenAI-compatible Portkey gateway URL and `@30875-fall26-openai/gpt-5-nano` model route with the existing `OPENAI_API_KEY`. No separate Portkey account or provider slug is required by the assignment example. | User supplied the assignment’s exact `base_url` and `MODEL` configuration on 2026-10-19 after the public OpenAI endpoint returned 401. | Supersedes D18’s public endpoint choice. The backend restricts the configured URL to the public OpenAI or Portkey API origins; a live university-gateway run completed with grounded evidence. |

## Implementation Decisions

These are recorded implementation choices within the authorized scope, not additional user-selected product requirements.

| ID | Choice and reason | Verification and limits |
| --- | --- | --- |
| T01 | Pydantic declarations are the source of shared contracts; export OpenAPI and generate TypeScript rather than maintaining duplicate definitions. | Snapshot/type generation and drift checks prepared. Contracts describe later behavior; only health is exposed now. |
| T02 | Use Next.js webpack mode for development and build after Turbopack CSS IPC was blocked in this environment. | Production build and browser tests passed. Framework stack is unchanged. |
| T03 | Use a server-side health proxy with server-controlled backend origin. Generate request IDs and log safe structured route templates; launch Uvicorn with `--no-access-log`. | Live connection, outage/retry, safe errors, redaction and actual log emission verified. Hosted access controls remain deferred. |
| T04 | Preserve aligned dependency versions rather than force the audit-suggested incompatible framework tooling downgrade. | Scoped security review found a development-only glob parser advisory; production audit reported zero vulnerabilities. Full audit remains affected; details in [Phase 1](phase-1.md). Recheck for a compatible patch. |
| T05 | Persist cleaned CSV plus per-version SQLite KPI/metadata files; activate through one master SQLite registry. | Smallest SRS-approved storage format; no Parquet dependency required. Immutable versions, reconciliation, activation and pinned reads were verified in Phase 2. |
| T06 | Rejected quality summaries distinguish excluded rows from unprocessed candidate rows, with zero accepted valid rows. | Prevents early rejection from labeling unprocessed rows as valid or inventing exclusions. Accepted datasets retain the original reconciliation rule. |
| T07 | Bound incoming body reads to 30 seconds and release the ingestion lock on timeout. | Fixes a stalled client blocking all subsequent local ingestion; backend and Next proxy deadline behavior is regression-tested. |
| T08 | Keep full category dictionaries and full source labels in stored metadata; return count-based UI quality with mapping dictionaries omitted and unusually long labels shortened with a flag. | Prevents valid high-cardinality data from activating successfully but appearing failed because its response exceeds the proxy limit. End-to-end contracts and tests match this public projection. |

## Evaluation Ownership

| Curator | Responsibility | Acceptance cases |
| --- | --- | --- |
| Ashutosh | Ingestion and data integrity | A01–A06; ingestion portions of A17–A18 |
| Abhee and Monisha | Analytics; individual split pending | A07–A09; analytics portions of A11 and A18 |
| Ashutosh | Agent behavior | A10, A12–A14; agent portions of A17 |
| All three | Integration, evaluation and demo | A11, A15–A16; remaining A17–A18 |

## Pending Decisions

Individual analytics case allocation, and D07/D08 operational details remain explicitly open until their affected work. Do not infer values from this log. Human contributions and future application tests are tasks, not missing product decisions.

GitHub publication exclusions are approved under D14. Publication progress and verification are tracked in the [live summary](summary.md).

## Phase 3 Implementation Decisions

| ID | Choice and reason | Verification and limits |
| --- | --- | --- |
| T09 | Reuse Phase 2 pinned dataset references and SQLite/CSV readers; implement deterministic analytics and the fixed baseline without dependencies or model calls. Archive self-contained HTML, SVG files and exact typed evidence using a staged directory and atomic publication. | Unit/integration tests verify eligibility, formulas, version replacement, snapshot pinning, escaping, and archive publication failure. Real January/February results match independent expected counts and both variance dimensions. |
| T10 | Compare durations in minutes and shares in percentage points. Restrict percentage-change/materiality fields to approved volume comparisons; unsupported relative percentages remain null with an explicit reason. | Regression tests guard small prior samples and share/duration units. Display floats with up to two decimals; evidence remains unrounded. |
| T11 | Preserve accepted station identifiers throughout analytics/evidence rather than introduce a new ingestion length restriction. | A 129-character accepted identifier now generates a report successfully; shared station/entity contracts no longer impose an incompatible 128-character maximum. |

## Phase 4 Implementation Decisions

| ID | Choice and reason | Verification and limits |
| --- | --- | --- |
| T12 | Reuse the fixed baseline’s pinned dataset references for every selected aggregate tool and archive the agent record under the baseline report ID. This keeps agent and fixed-workflow formulas, versions, and evidence directly comparable. | Pinned replacement tests and the real-data injected-model run passed. |
| T13 | Use a bounded typed state machine: six LLM calls, ten selected tool calls, strict route/plan/follow-up/claim schemas, one retry per gate, and Python-only claim rendering. Reject failed or incomplete evidence before it is streamed as successful. | Wrong period/station, forged evidence, budget, malformed output, incomplete follow-up, and grounding tests passed. |
| T14 | Stream safe stage and validated aggregate events as NDJSON through a server-origin Next.js proxy; show the final HTML in a sandboxed iframe. Original provider choice used Portkey credentials in environment variables. | UI, proxy, backend stream, and browser tests passed. Provider choice superseded by D18/T15; streaming and safe fallback remain. |
| T15 | Call the OpenAI Chat Completions API directly with a backend-only `OPENAI_API_KEY`, retaining strict schemas, safe errors, and the existing bounded state machine. | User-directed D18. Mock-transport tests assert the direct endpoint and bearer header. Superseded by D19/T16 for the university endpoint. |
| T16 | Read `OPENAI_BASE_URL` and `OPENAI_MODEL` from backend environment; allow only the known public OpenAI and university Portkey API origins. Keep the existing bearer-key, strict-schema, and safe-fallback behavior. | Gateway URL/model mock tests pass; live gateway run completed with three successful aggregate tools and a grounded archived report. |
| T17 | Restrict model planning to approved tool names and a follow-up station ID. Python binds pinned periods and remaining arguments, and supplies exact eligible claim candidates for final selection. | Prevented generic model arguments and unsupported claim fields in live attempts; final run completed with four model calls and no validation error. Full grounding checks remain in force. |
