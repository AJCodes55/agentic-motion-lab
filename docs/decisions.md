# Project Decisions

Last updated: 2026-10-18.

This is the canonical project-wide decision record. Update it after every crucial decision. Record what changed, why, approval/source, affected phase, and unresolved details. Preserve superseded decisions explicitly; do not silently replace them. The [SRS](../software_requirement_specification_srs.md) remains the requirements authority. Update affected requirements and the [live summary](summary.md) when a decision changes behavior or scope.

## Approved Product Decisions

All entries below were confirmed by the user on 2026-10-18. D01–D08 preserve the IDs from the original Phase 0 register.

| ID | Decision | Reason or source | Scope and remaining details |
| --- | --- | --- | --- |
| D01 | Accept one or two uploaded files, including two different months. Group and validate each month separately. Accept canonical `JC-YYYYMM-citibike-tripdata.csv` and both verified ZIP suffixes (`.zip` and `.csv.zip` after `tripdata`). Process uploaded files and CSV members alphabetically, preserving row order. Ignore macOS metadata. | User clarified file count and approved all recommendations; source packaging verified. | Phase 2. Other multipart naming variants remain unapproved. Atomic activation across two different months is not specified. |
| D02 | Display all equally highest eligible contributing categories; explicitly label unclassified contributions when Unknown ties. Never arbitrarily choose one or sum overlapping dimensions. | User approved joint representation. | Phase 3/4. Exact tie wording and claim representation remain pending before implementation. |
| D03 | Align daily charts by day number; missing days in the shorter month are gaps, never zero. | User approved recommendation for unequal month lengths. | Phase 3. January has 31 days; February 2026 has 28. |
| D04 | Require an explicit reporting month and any station needed for station-specific requests. Ask users to select among ambiguous station matches. Retain no analytical chat context. | User confirmed month provision and approved request-context recommendation. | Phases 1, 4–5. Aggregate reports require no station; no omitted-month default is approved. |
| D05 | Keep Phase 0 records in `docs/phase-0/`. Use `docs/summary.md` for live progress and `docs/decisions.md` for crucial project decisions. | User approved documentation location, then requested ongoing summary and decision files. | All phases. Update summary after every phase/important step and decisions after every crucial decision. |
| D06 | Abhee and Monisha own analytics evaluation. Ashutosh owns ingestion and agent behavior evaluation. | Explicit named assignments supersede the earlier proposed user/colleague role allocation. | Individual analytics case split remains pending. All three still contribute challenging cases; approval is not evidence of individual authorship. |
| D07 | Target a hosted application. | User confirmed eventual hosting. | Provider, authentication/isolation, concurrency, byte/expansion limits, latency/cost targets, backup and recovery remain pending before affected implementation or exposure. |
| D08 | Retain data for at most six months. | User specified maximum retention. | Retention clock and coverage of sources, versions, traces, reports and evidence remain pending; reconcile expiry with archive requirements before implementation. |
| D09 | Use January 2026 as prior and February 2026 as current for study, evaluation and primary demo; exclude the local August file. | User's revised plan and SRS. | Verified sources and counts are in the [manifest](phase-0/dataset-manifest.md). |
| D10 | Fetch requested source data from the public Citi Bike S3 bucket. | User identified the public source. | Source download only; application cloud storage remains outside approved scope. |
| D11 | Map `member`/`casual` to Member/Casual and `classic_bike`/`electric_bike` to Classic/E-bike; other values become Unknown. | User confirmed mappings. | Preserve Unknown in totals and denominators; exact source values/counts recorded in the manifest. |
| D12 | Render values with up to two decimal places; retain unrounded evidence. | User specified display precision; SRS requires exact grounding/thresholds. | Applies to analytics, charts, reports and claims. |
| D13 | Approve all 44 boundary case specifications. | User explicitly stated that everything was reviewed and approved. | Supersedes initial I01–I03-only approval. Application execution and individual curator contributions are separate work. See [review record](phase-0/boundary-review-cases.md). |
| D14 | Publish application source, tests, CI, locks, contracts and current documentation to `AJCodes55/agentic-motion-lab`; exclude downloadable raw datasets, superseded planning/conversation files, local assistant/editor configuration, secrets, dependencies and generated build/cache files. Keep `.env.example` and generated shared API types. | User explicitly approved the proposed exclusion list before publication. | Initial publish contains 42 files, under 0.5 MB. [Ignore rules](../.gitignore) enforce the exclusions. |

## Implementation Decisions

These are recorded implementation choices within the authorized scope, not additional user-selected product requirements.

| ID | Choice and reason | Verification and limits |
| --- | --- | --- |
| T01 | Pydantic declarations are the source of shared contracts; export OpenAPI and generate TypeScript rather than maintaining duplicate definitions. | Snapshot/type generation and drift checks prepared. Contracts describe later behavior; only health is exposed now. |
| T02 | Use Next.js webpack mode for development and build after Turbopack CSS IPC was blocked in this environment. | Production build and browser tests passed. Framework stack is unchanged. |
| T03 | Use a server-side health proxy with server-controlled backend origin. Generate request IDs and log safe structured route templates; launch Uvicorn with `--no-access-log`. | Live connection, outage/retry, safe errors, redaction and actual log emission verified. Hosted access controls remain deferred. |
| T04 | Preserve aligned dependency versions rather than force the audit-suggested incompatible framework tooling downgrade. | Scoped security review found a development-only glob parser advisory; production audit reported zero vulnerabilities. Full audit remains affected; details in [Phase 1](phase-1.md). Recheck for a compatible patch. |

## Evaluation Ownership

| Curator | Responsibility | Acceptance cases |
| --- | --- | --- |
| Ashutosh | Ingestion and data integrity | A01–A06; ingestion portions of A17–A18 |
| Abhee and Monisha | Analytics; individual split pending | A07–A09; analytics portions of A11 and A18 |
| Ashutosh | Agent behavior | A10, A12–A14; agent portions of A17 |
| All three | Integration, evaluation and demo | A11, A15–A16; remaining A17–A18 |

## Pending Decisions

Exact tie rendering/claim contracts, individual analytics case allocation, and D07/D08 operational details remain explicitly open until their affected work. Do not infer values from this log. Human contributions and future application tests are tasks, not missing product decisions.

GitHub publication exclusions are approved under D14. Publication progress and verification are tracked in the [live summary](summary.md).
