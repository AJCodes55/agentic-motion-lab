# Project Decisions

Last updated: 2026-10-24.

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

## Phase 6 Scope Decisions — 2026-10-22

| ID | Decision | Reason or source | Scope and remaining details |
| --- | --- | --- | --- |
| D20 | Keep Phase 6 local and single-user for now. Hosting remains future work. The eventual system must support 100+ users. | User explicitly chose local single-user scope during Phase 6 and stated the future scale goal. | D07's hosted destination remains the long-term target. 100+ users is a goal, not demonstrated capacity or a defined simultaneous workload. Provider, storage topology, identity/isolation and load acceptance criteria remain unselected. |
| D21 | Defer hosted concurrency, retention details, backup and recovery policies; document deployment gates and remaining Phase 6 work in the implementation plan. | User explicitly deferred these policies during Phase 6. | D08's maximum six months remains approved. No retention clock, artifact/backup lifecycle, destructive cleanup, backup destination/schedule or RPO/RTO is inferred. These deferred tasks do not block independent local polish and verification. |

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
| T16 | Read `OPENAI_BASE_URL` and `OPENAI_MODEL` from backend environment; allow only the known public OpenAI and university Portkey API origins. Keep the existing bearer-key, strict-schema, and safe-fallback behavior. | Gateway URL/model mock tests pass; live backend and browser runs completed with the university gateway, a qualifying variance follow-up, and a grounded report. |
| T17 | Restrict model planning to approved tool names and a follow-up station ID. Python binds pinned periods and remaining arguments, and supplies exact eligible claim candidates for final selection. | Prevented generic model arguments and unsupported claim fields in live attempts; final run completed with four model calls and no validation error. Full grounding checks remain in force. |
| T18 | Run browser E2E checks against a built production frontend, with an isolated backend store and validated optional port overrides. | A retained trace showed Next.js development Fast Refresh reloading the page during a parallel ingestion test. Four subsequent three-worker runs passed (16/16 tests); hosted behavior remains separately scoped. |

## Phase 5 Implementation Decisions

| ID | Choice and reason | Verification and limits |
| --- | --- | --- |
| T19 | Provide strict structured ad-hoc requests and typed extraction from the existing command input. The four aggregate metric families are single-month only; station starts supports the immediately preceding month. Keep D04's explicit reporting month and station selection, with no retained analytical conversation context. | Request validation, refusal categories, conflicting reporting periods, long station IDs, and complete ambiguity resubmission are regression-tested. Natural-language classification remains model-dependent; structured queries avoid that dependency. |
| T20 | Reuse a single baseline snapshot for station lookup, calculations, answer tables, and fixed SVG charts. A chart consumes successful evidence from the same run; archive the exact result, evidence, and SVG with a manifest published last. | Tests verify exact chart/answer values, Unknown shares, pinned replacements, escaped labels, invalid evidence rejection, and failed-write cleanup. No arbitrary chart code or paths are exposed. |
| T21 | Browse one final saved report per run, preferring its ad-hoc artifact, then agent artifact, then baseline. Read saved HTML directly and validate its identity against the baseline's pinned dataset references. | Original baseline HTML/evidence remain saved. History tests cover single-month subsets with both months loaded, replacement immutability, metadata/HTML mismatch, path traversal, and symlinks. Hosting, access controls and retention remain deferred. |

## Phase 6 Implementation Decisions

| ID | Choice and reason | Verification and limits |
| --- | --- | --- |
| T22 | Apply interface and newly generated report polish within existing contracts, using native semantic controls and existing styling. Preserve explicit request context, validated-only activity, grounding, evidence identity and immutable saved reports. | Verification is tracked in [Phase 6](phase-6.md). Existing archives are not rewritten. |
| T23 | Proceed with approved local limits and isolated recovery verification while operational product policies remain unresolved. Do not infer a retention clock, delete inactive versions, expose a hosted service or invent authentication/isolation rules. | D07/D08 remain open. Hosting/provider, intended users/isolation, hosted workload/concurrency, retention clock and artifact/backup coverage, backup destination/schedule, acceptable data loss and restore-time targets require decisions before their affected behavior. |

## Vercel Preparation Scope — 2026-10-24

| ID | Decision | Reason or source | Scope and remaining details |
| --- | --- | --- | --- |
| D22 | Prepare Vercel Services configuration now; decide durable backend storage next. | User explicitly selected this scope after the SQLite/filesystem constraint was explained. | Extends D20 with authorized hosting preparation only. No deployment, data migration or ephemeral-storage substitution is authorized by this choice. Existing retention/access/capacity gates remain. |

Service names `backend`/`frontend`, public catch-all to `frontend` (including its existing `/api/*` proxies), and caller-side `frontend` → `backend` binding `BACKEND_URL` were approved by the user on 2026-10-24 (D23). See the Vercel section of [Phase 6](phase-6.md) for persistence, upload transport and access blockers.

| ID | Decision | Reason or source | Scope and remaining details |
| --- | --- | --- | --- |
| D23 | Approve the proposed service names, frontend-owned public routing and frontend-to-private-backend binding. | User answered “1) approve” to the deployment checklist on 2026-10-24. | Configuration approval only; durable hosting/storage and actual deployment remain outstanding. |
| D24 | Intended hosted use is demonstrations and sharing with recruiters. | User explicitly described the audience on 2026-10-24. | Does not establish anonymous write/model access, authentication policy, simultaneous workload or paid-hosting budget. Future 100+ user goal remains distinct from verified demo capacity. |

## Deployment Deferred to Final Stage — 2026-10-24

| ID | Decision | Reason or source | Scope and remaining details |
| --- | --- | --- | --- |
| D25 | Continue local development and evaluation; move hosted deployment to the final stage after Phase 7. Revisit hosting when Render credits activate and the user asks to resume deployment. | User explicitly requested postponement because their Render credits are not yet activated. | Supersedes deployment as the immediate next task under D22. Preserve prepared Vercel configuration and D23 routing approval as prior work; neither establishes a Render configuration or a completed deployment. Render was recommended for a persistent-disk demo but its plan, cost and final topology are not yet approved. Credit activation alone does not authorize spending or deployment. |

On return, read the final deployment stage in [the implementation plan](../implementation_plan.md). Confirm credits/budget and hosting topology; resolve persistence, upload transport, access protection, concurrency and retention/backup/recovery gates; then configure, test and deploy only within the user's renewed authorization. The demo/recruiter audience (D24), future 100+ user goal and existing grounding/provenance safeguards remain unchanged. No cloud resources, data migration, commit or push is authorized by this deferral.

## Local Operational Policies — 2026-10-24

| ID | Decision | Reason or source | Scope and remaining details |
| --- | --- | --- | --- |
| D26 | Retain each uploaded dataset version for six calendar months from its upload timestamp, not its reporting month; expire dependent reports, KPIs, charts and evidence, and delete expired data/reports through reference-safe cleanup. | User explicitly confirmed January 2026 data uploaded in October 2026 expires in April 2027 and approved deleting old data/reports. | UTC timestamps; preserve the day/time where possible and clamp a nonexistent month-end day. Whole report archives expire with their earliest-expiring required baseline dataset, including agent/ad-hoc siblings. Rejections/quarantine receive their own upload clocks. This resolves the local clock/coverage portion of D08/D21; hosted scheduling and external backup lifecycle still require deployment setup. |
| D27 | Create backups before risky changes and after important demo preparation; restore into a new directory and never overwrite the only surviving copy. | User approved this procedure explicitly. | Local tools take an explicit external destination path; no location, unattended schedule, cloud account or storage purchase is assumed. Preserve original retention dates and reject expired managed snapshots rather than resurrect expired data. Managed snapshot expiry is its earliest known artifact expiry. |
| D28 | Target at most 24 hours of lost changes (RPO) and recovery within one hour (RTO). | User explicitly accepted the targets and that verification requires testing. | Local measured fixtures establish mechanics and observed timing only. Event-triggered backups alone do not guarantee 24-hour freshness; daily backups during changes and freshness checks are necessary. Host/hardware loss and deployed scale remain unverified. |
| D29 | Preserve legacy uploads without recorded upload timestamps until the user supplies original upload dates. | User explicitly chose this safe handling in the follow-up question. | Never infer original upload dates from reporting months or filesystem mtimes; do not start a new six-month clock on restore or merely opening old data. Unknown/incomplete artifacts are inventoried and retained, not treated as proven orphans. |

D25 still defers hosted deployment. D26–D29 reopen and authorize completion of local Phase 6 operational work; deferring deployment does not mean these requirements were implemented. Existing local datasets are not purged as part of development verification; destructive operations are tested only on isolated fixtures.

## Local Backup Destination — 2026-10-24

| ID | Decision | Reason or source | Scope and remaining details |
| --- | --- | --- | --- |
| D30 | Use `~/Main drive/agentic-motion-lab backup` as the local backup parent directory. | User supplied this folder under their Main drive. | Path is outside the repository and default working data root with no symlink components; the corrected directory already exists. Its existing parent is on the same filesystem as the working data. This protects against some accidental changes, not failure/loss of that filesystem or machine. No folder or backup was created during path validation; creation outside the workspace requires the applicable filesystem permission. |
