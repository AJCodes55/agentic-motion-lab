# Implementation Plan: Agentic Monthly Mobility Reporting Workflow

**Source:** [Software Requirements Specification](software_requirement_specification_srs.md)

**Status:** Phase 0 started with explicit user authorization. Source inspection and acceptance planning are linked below. Phase 0 preparation is complete; all 44 review cases are user-approved. Phases 1–3 are implemented and locally verified. Deferred decisions remain gated before affected implementation.

**Live records:** Update [summary](docs/summary.md) after every phase and important step. Update [decisions](docs/decisions.md) after every crucial decision, including changes and superseded choices.

**Overall complexity:** High, primarily because storage consistency, numerical correctness, and agent validation must work together.

## 1. Delivery Approach

Build a reliable reporting foundation first, then add the agent, then polish and evaluate the complete product. Calculations, grounding, and safe failure behavior belong in the MVP, not a later cleanup phase.

At planning time, the workspace contained requirements and proposal documents, with no application code or tests. There were no existing naming, logging, error-handling, data-access, or testing patterns to mirror. The SRS is the source of truth. The organization below is proposed, not an existing repository convention.

## 2. Delivery Milestones

| Milestone | Completed phases | Demonstrable outcome |
| --- | --- | --- |
| Barebones setup | 0–1 | Frontend and backend run and communicate |
| Reliable reporting baseline | 2–3 | Upload → cleaned data → verified dashboard |
| Agentic MVP | 4 | Initial analysis → adaptive investigation → grounded report |
| Feature-complete version | 5 | Supported ad-hoc questions, charts, and archived reports |
| Polished release candidate | 6–7 | Usable interface, evaluated behavior, repeatable demo |

## 3. Phase 0 — Finalize Inputs and Acceptance Rules

### Tasks

- Use the confirmed Jersey City months: **January 2026 (prior) and February 2026 (current)** for study, evaluation, and the primary demo. August 2026 is outside the selected dataset, even if an August file exists locally.
- Verify the official source files and URLs for those two months; record actual archive/member names rather than assuming their packaging.
- Document archive members, filename variants, processing order, checksums, and expected counts.
- Confirm source category mappings, including Unknown.
- Resolve contribution ties, display precision, and daily-chart alignment across unequal month lengths.
- Define behavior for omitted months, ambiguous station names, and conversational context.
- Establish deployment scope, authentication needs, upload limits, concurrency expectations, and retention.
- Assign all three members to curate evaluation cases.
- Create a requirements checklist connecting each SRS rule to its implementation phase and acceptance case.

### Deliverables

Dataset manifest, decision register, and acceptance checklist in an agreed documentation location.

### Phase 0 Records

- [Dataset manifest](docs/phase-0/dataset-manifest.md): verified January/February source archives, members, checksums, counts, and category dictionary.
- [Decision register](docs/decisions.md): approved upload, tie, chart, request, documentation, and evaluation rules; deferred operational decisions.
- [Acceptance checklist](docs/phase-0/acceptance-checklist.md): 18 requirement-linked acceptance cases and curator responsibilities.
- [Checked cleaning results](docs/phase-0/cleaned-expectations.md): independently cross-checked monthly totals, reconciliations, and the real demo candidate, with aggregate JSON evidence.

- [Boundary review pack](docs/phase-0/boundary-review-cases.md): 44 synthetic case specifications with expected results and requested reviewers.

### Exit Condition and Progress

No unresolved decision is silently replaced by a coding assumption. User approved all five recommendations on 2026-10-18. Source inspection, initial traceability, and role assignments are complete. Curators are Abhee and Monisha (analytics), and Ashutosh (ingestion and agent behavior). Cleaned totals and the real demo candidate are independently cross-checked and recorded. All 44 assistant-prepared boundary cases are user-reviewed and approved; arithmetic checks pass. Phase 0 preparation is complete. Individual analytics case allocation and contributions by all three curators remain evaluation work; tie wording and structured leaders were approved under D17 when Phase 3 began. Operational choices remain explicitly deferred until their affected phase. Approval is not represented as completed application tests or individual curator authorship.

## 4. Phase 1 — Barebones Application and Contracts

**Status:** Complete for local foundation scope on 2026-10-18. See [setup and verification](docs/phase-1.md). FastAPI and Next.js communicate; the unavailable-service state and retry are verified. Backend: 17 tests, 99.33% coverage. Frontend: 11 tests, 100% line coverage and 90.9% branch coverage. Two browser tests, lint, typecheck, and production build pass. At the Phase 1 checkpoint, ingestion, analytics, and LLM processing were not yet implemented. Hosted deployment remains gated on deferred operational decisions.

### Features and Tasks

- Set up Next.js/Tailwind frontend and FastAPI backend.
- Establish configuration, dependency management, and secret handling.
- Build the basic page layout: upload area, reporting-period selector, command input, progress area, and report viewer.
- Define shared contracts for requests, periods, dataset versions, quality summaries, tool results, claims, and errors.
- Establish structured logs, run IDs, and consistent API error responses.
- Configure unit, integration, and E2E testing plus automated checks.

### Proposed Organization

Separate frontend and backend applications, with backend modules for ingestion, storage, analytics, agents, reports, and evaluation. These are proposed conventions, not existing repository patterns.

### Exit Condition

Both applications start reliably; the frontend reaches the backend and displays a clear service error when unavailable.

## 5. Phase 2 — Ingestion, Cleaning, and Safe Storage

**Status:** Complete for local development on 2026-10-18. [Verification and usage](docs/phase-2.md): 83 backend tests (94.70% coverage), 29 frontend tests (100% line coverage), three live browser tests, lint/typecheck/build passed. Real January/February uploads activate reconciled versions with 39,198/25,387 valid trips. Rejected corrections preserve active versions. Hosted operational decisions remain deferred.

### Features and Tasks

- Implement CSV and ZIP validation, safe extraction, schema checks, and all-member concatenation.
- Apply the exact cleaning sequence and threshold denominators.
- Produce stage-wise quality summaries and reconciliation checks.
- Store cleaned data and monthly KPIs in immutable dataset versions.
- Implement transactional activation through the master version registry.
- Support corrected uploads without changing active data until validation succeeds.
- Pin dataset versions for report runs and preserve historical evidence.
- Show accepted/rejected ingestion results in the UI.

### Validation

- Test exact 1% and 5% boundaries, duplicate IDs across files, duration boundaries, Unknown categories, and empty datasets.
- Verify reconciliation across CSVs, cleaned data, and SQLite.
- Simulate interruption before and after activation.

### Exit Condition

A failed upload preserves the previous version; a successful upload activates matching trip data and KPIs.

## 6. Phase 3 — Deterministic Analytics and Fixed Baseline

**Status:** Complete for local development on 2026-10-18 and published with Phases 2–4 in commit `53c569a`. Five-section zero-LLM dashboard, analytics/variance, immutable archives, and UI verified. Backend: 103 tests, 95.91% coverage; frontend: 35 tests; three browser tests, lint/typecheck/build and reviews passed. Real January/February totals, daily starts and both candidate variance dimensions match independent expectations. D17 resolves ties. See [Phase 3](docs/phase-3.md).

### Features and Tasks

- Implement the approved KPIs, daily counts, station rankings, period comparisons, and contribution calculations.
- Implement `station_movers`, including candidate selection across all stations.
- Implement `analyze_station_variance` with both required breakdown dimensions.
- Enforce sample eligibility, new/removed handling, materiality, and tie rules.
- Build `generate_standard_dashboard` with all five report sections.
- Support standalone reports when prior-month data is missing.
- Save report HTML, chart assets, dataset references, and baseline evidence.
- Establish this workflow as the fixed evaluation comparator.

### Validation

- Compare results against independently checked fixtures.
- Test candidate selection outside the displayed top five.
- Test contribution thresholds, zero denominators, and Unknown dominance.

### Exit Condition

Without any LLM calls, an accepted upload produces a correct, reproducible report.

## 7. Phase 4 — Agentic MVP with Grounding

**Status:** Implemented, committed, and verified with an injected deterministic model, a live university-gateway run, and a live browser workflow. See [Phase 4 evidence](docs/phase-4.md).

### Features and Tasks

- Integrate the university-provided `@30875-fall26-openai/gpt-5-nano` route through its OpenAI-compatible Portkey gateway with aggregate-only context. Keep `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` in the backend environment.
- Implement routing, available-period lookup, static context retrieval, and plan validation.
- Restrict model planning to approved tool names and follow-up station choice; bind periods and remaining arguments in Python from pinned snapshots.
- Build the bounded execution state machine.
- Let the agent inspect station movers and select the required variance investigation.
- Validate successful follow-up for the correct station, both periods, and both dimensions.
- Build exact claim candidates from successful aggregate evidence, restrict model selection to those candidates, and check complete evidence identity.
- Render narrative exclusively through Python templates and transition enums.
- Enforce ten tool calls, six LLM calls, and one retry per gate.
- Implement the exact baseline-only warning states.
- Display the four UI stages and adaptive-follow-up indicator.

### Validation

- Reject a correct number attached to the wrong month or station.
- Reject forged evidence, unsupported claims, and incomplete follow-ups.
- Verify retry accounting and budget exhaustion.
- Confirm no invalid narrative appears in the UI.

### Exit Condition — Agentic MVP

Upload a month, generate the baseline, observe a qualifying decline, watch the agent investigate it, and receive either a fully validated report or the deterministic fallback.

## 8. Phase 5 — Supported Ad-Hoc Features

**Status:** Complete and locally verified on 2026-10-22. Four single-month metric families, station starts and adjacent comparisons, explicit ambiguity selection, evidence-backed charts, refusals and immutable history access are implemented. Backend: 201 tests, 94.48% coverage; frontend: 64 tests, 84.69% branch coverage; all six browser tests, lint, typecheck, production build and reviews passed. Publication authorized on 2026-10-22. See [Phase 5 verification](docs/phase-5.md).

### Features and Tasks

- Add all four supported single-month metric queries.
- Add station-specific queries and adjacent-month comparisons.
- Implement station lookup using the approved ambiguity rules.
- Add approved ad-hoc charts through `make_chart`.
- Implement explicit refusals for unsupported metrics, causal questions, forecasting, non-adjacent comparisons, and missing comparison data.
- Add report-history browsing and archived report access.
- Apply the chosen conversation-context policy.

### Validation

- Test each supported request family and refusal category.
- Confirm charts use the same verified results as displayed answers.
- Ensure corrected datasets do not rewrite archived reports.

### Exit Condition

The application covers the complete agreed analytical scope, with clear boundaries.

## 9. Phase 6 — Interface Polish and Operational Hardening

### Features and Tasks

- Improve loading, empty, rejected-upload, unavailable-period, and partial-report states.
- Make quality summaries and tool traces understandable without exposing private model reasoning.
- Improve keyboard navigation, accessibility, responsive layouts, chart labels, and report readability.
- Implement the approved authentication and user-isolation requirements.
- Enforce upload, archive-expansion, and concurrency limits.
- Add recovery procedures, backup/restore verification, and safe orphan-version cleanup.
- Measure latency and cost; optimize using observed bottlenecks.

### Exit Condition

The product is usable and recoverable under the agreed operating conditions. Production deployment remains gated on the unresolved operational choices being approved and verified.

## 10. Phase 7 — Evaluation and Demonstration

Evaluation fixtures begin in Phase 0; this phase completes the comparative assessment.

### Tasks

- Run the fixed baseline and agent workflow against identical dataset versions and analytical tools.
- Execute challenging cases contributed by all three members.
- Record correctness, attribution failures, follow-up completion, refusals, latency, calls, and available cost information.
- Explain what useful decomposition the agent adds beyond the preset dashboard.
- Complete unit, integration, and E2E checks, targeting at least 80% coverage.
- Rehearse the upload → initial result → selected breakdown → validated report demo, using January 2026 as the prior month and February 2026 as the new upload.
- Demonstrate wrong-month rejection and baseline-only fallback.
- Document limitations and release evidence.

### Exit Condition

Another team member can reproduce the demo and evaluation from the documented inputs.

## 11. Main Risks and Controls

| Risk | Control |
| --- | --- |
| Source files differ from expected naming/schema | Inspect selected files and finalize the manifest before ingestion implementation |
| AI selects the wrong evidence | Composite-identity grounding and adversarial fixtures |
| Mandatory investigation exceeds budget | Test representative call sequences early; retain enforced limits and deterministic fallback |
| Replacement mixes dataset versions | Immutable artifacts, transactional activation, and pinned run references |
| Agent adds little beyond preset analysis | Measure verified follow-up decomposition against the identical fixed baseline |
| Deployment scope expands late | Resolve operational requirements before Phase 6 |

## 12. Dependencies and Implementation Gate

**Phase sequence:** 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7.

Testing and evaluation preparation run throughout; they are not postponed until the end. Each phase must satisfy its exit condition before dependent functionality is considered complete.

The user authorized Phase 0 execution and subsequently approved all review cases and instructed work to proceed to Phase 1. Saving this roadmap alone does not authorize other later phases. Phase 0 decisions and acceptance preparation must satisfy the gate above before dependent development begins.
