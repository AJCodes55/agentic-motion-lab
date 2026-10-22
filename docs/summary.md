# Live Project Summary

Last updated: 2026-10-19.

## Update Rule

Update this file after every phase and every important step: implementation changes, verified results, approvals, blockers, and changes in scope. Record the outcome, verification, remaining work, and next step. Update [decisions.md](decisions.md) whenever a crucial decision is made or changed. Keep detailed evidence in its existing document and link it here.

## Current State

| Phase | Status | Result |
| --- | --- | --- |
| 0 — Inputs and acceptance preparation | Complete for preparation scope | Sources checked, decisions recorded, curators assigned, all 44 case specifications user-approved. Individual curator contributions remain evaluation work. |
| 1 — Application foundation | Complete and locally verified | Next.js/Tailwind frontend connects to FastAPI; service outage and retry states verified. |
| 2 — Ingestion, cleaning, storage | Complete for local development | Upload/public-source fetch, exact cleaning, quality display, immutable CSV/SQLite versions, atomic activation and pinned reads are verified. See [Phase 2](phase-2.md). |
| 3 — Deterministic analytics and fixed baseline | Complete for local development | Five-section zero-LLM reports, analytics, variance, archived evidence/assets, and report UI verified. See [Phase 3](phase-3.md). |
| 4 — Agentic workflow and grounding | Locally verified with injected model and live university gateway | Bounded workflow, validated adaptive follow-up, grounded narrative, safe fallback and streamed UI are implemented. See [Phase 4](phase-4.md). |
| 5–7 — Features, hardening, evaluation | Not started | Follow the [implementation plan](../implementation_plan.md). |

## Important Steps Completed

| Date | Step | Result and evidence |
| --- | --- | --- |
| 2026-10-18 | Verified official January/February source files | File names, ZIP members, checksums, schemas and category counts recorded in the [dataset manifest](phase-0/dataset-manifest.md). |
| 2026-10-18 | Cross-checked cleaning results | January: 40,044 source rows → 39,198 valid trips. February: 25,809 → 25,387. Independent Python and SQLite calculations agreed on retained rows. See [checked results](phase-0/cleaned-expectations.md). |
| 2026-10-18 | Confirmed real demo candidate | River St & Newark St (`HB106`): 1,584 → 866 starts, down 718 trips (45.33%). Both variance dimensions recorded in the checked results. |
| 2026-10-18 | Prepared acceptance and review cases | [18 acceptance mappings](phase-0/acceptance-checklist.md) and [44 boundary specifications](phase-0/boundary-review-cases.md). User explicitly approved the full pack; these specifications are not executed application tests. |
| 2026-10-18 | Implemented local application foundation | Health endpoint, strict shared contracts, generated frontend types, safe errors, request IDs, structured logs, and basic interface. See [Phase 1 setup](phase-1.md). |
| 2026-10-18 | Verified foundation | Backend: 17 tests, 99.33% coverage. Frontend: 11 tests, 100% line coverage, 90.9% branch coverage. Two browser tests, lint, typecheck, and production build passed. Code/security reviews completed. |
| 2026-10-18 | Resolved build and logging issues | Selected supported webpack mode after Turbopack IPC failures; verified actual structured-log emission and disabled unredacted server access logs in documented launch commands. |
| 2026-10-18 | Established live documentation | This summary tracks progress; [decisions.md](decisions.md) is the project-wide decision record. |
| 2026-10-18 | Prepared initial GitHub publication | Target: `AJCodes55/agentic-motion-lab`, verified empty before publication. User approved the exclusions. Ignore rules retain 42 application/documentation files, under 0.5 MB. Pattern scan found no matching credentials or local absolute user paths. Python dependency audit found no known vulnerabilities; production npm audit is clean and the known development advisory remains documented. Type checking passes in a clean approved-file copy. |
| 2026-10-18 | Committed and pushed approved files | Initial commit [`ff00165`](https://github.com/AJCodes55/agentic-motion-lab/commit/ff0016573e907aaf3c3fa94b54d4ba38b685b33f) was pushed to `main`; local branch tracks `origin/main`. All 42 approved files are published. GitHub [automated checks](https://github.com/AJCodes55/agentic-motion-lab/actions/runs/39163539007) started and were in progress at this update. This documentation follow-up records the completed publication. |
| 2026-10-18 | Approved Phase 2 operating rules | User approved 25 MB/file, 50 MB total, 200 MB expanded, 100 CSV members, one ingestion, and independent acceptance per month; decisions D15–D16. |
| 2026-10-18 | Implemented and reviewed Phase 2 | Safe uploads/fetch, cleaning, persisted quality/quarantine, immutable Raw Lake/KPI versions, registry activation and UI integrated. Fixed identifier reload, malformed-member budget interference, stalled-body locking and oversized dictionary responses; regression tests pass. |
| 2026-10-18 | Completed Phase 2 verification | 83 backend tests (94.70% coverage), 29 frontend tests (100% lines), three browser tests, lint/typecheck/build passed. Real two-month upload/storage check matches 39,198 January and 25,387 February valid trips. [Results and scope](phase-2.md). |
| 2026-10-18 | Started Phase 3 and resolved contribution ties | User authorized deterministic analytics and baseline implementation. D17 records approved wording and structured tied leaders; no LLM integration or publication is included. [Phase 3 work](phase-3.md). |
| 2026-10-18 | Completed Phase 3 verification | 103 backend tests (95.91% coverage), 35 frontend tests, three browser tests, lint/typecheck/build and reviews passed. Real totals, every daily count, HB106 candidate, and both variance dimensions match independent results. Reports use zero LLM calls; HTML/SVG/evidence archives preserve pinned versions. [Verification and usage](phase-3.md). |

| 2026-10-18 | Started Phase 4 | User authorized the agentic MVP. Existing uncommitted Phase 2–3 work is preserved. Design uses a single pinned baseline snapshot for agent tools; local provider credentials were expected for live verification at this step; D18 later changed the provider path. |
| 2026-10-19 | Verified Phase 4 locally | At this checkpoint, 154 backend tests (94.44% coverage), 45 frontend tests (82.25% branch coverage), four browser tests, lint/typecheck/build passed. Cached real-data run with an injected model selected HB106 (1,584 → 866), included both variance dimensions, and archived matching artifacts. [Phase 4 evidence](phase-4.md). Live gateway verification followed on 2026-10-21. |

| 2026-10-19 | Switched Phase 4 to direct OpenAI | User replaced the Portkey requirement with direct use of the university OpenAI key (D18). Backend provider and tests now use a single `OPENAI_API_KEY`; SRS, implementation plan, and Phase 4 guide were updated. |
| 2026-10-19 | Checked live authentication | Loaded the verified public January/February archives into the local backend (39,198 and 25,387 valid trips). One live agent request safely fell back to baseline after its first provider call. A no-dataset model-access check returned HTTP 401 `invalid_api_key` from the public OpenAI endpoint. The university key may require a gateway URL; see [Phase 4](phase-4.md). |

| 2026-10-19 | Configured university gateway | User supplied `https://api.portkey.ai/v1` and `@30875-fall26-openai/gpt-5-nano` from assignment code. Backend configuration, example environment, tests, SRS and plan now reflect this route (D19). Key value was preserved locally and not printed. |
| 2026-10-21 | Verified live Phase 4 run | University gateway run completed on verified public January/February data: HB106, 1,584 → 866 starts, both variance dimensions, grounded Member wording, and matching archived report. Four model and three successful tool calls; 3,740 input and 413 output tokens. Backend: 156 tests, 94.56% coverage. [Evidence](phase-4.md). |
| 2026-10-22 | Completed Phase 4 browser checks | All four browser tests passed sequentially on isolated ports. One separate live UI request reached the university gateway and displayed HB106, the variance follow-up, and Member wording. A concurrent browser run had one ingestion UI timing failure; its isolated and sequential reruns passed. [Evidence](phase-4.md). |

## Remaining Work and Limits

Local preview started on 2026-10-18: frontend `http://127.0.0.1:3000`, backend `http://127.0.0.1:8000`. Process availability depends on them remaining active, and a running backend must be restarted to load newer code and environment. Separate live gateway and browser checks succeeded. No embedding model is currently selected or implemented.

- Phases 2–4 are implemented and published in commit `53c569a`. The public OpenAI endpoint rejected the university key; the supplied university Portkey gateway URL and model route completed live backend and browser checks.
- Tied-contribution wording and structured leaders approved under D17; allocate individual analytics cases and obtain challenging contributions from each curator during evaluation preparation.
- Resolve hosting/access controls, resource limits, recovery, and retention details before the affected implementation or exposure.
- Track the development dependency advisory described in [Phase 1](phase-1.md). Production npm audit reported zero vulnerabilities at the recorded check; full development audit was not clean.
- Phase 2–3 verification is local; remote CI will run after a requested commit/push. No hosted deployment has occurred. Isolated test servers were stopped; a separate local user preview was subsequently started as noted above. Historic Phase 1 CI links remain above.

## Next Step

Next: prepare Phase 5 or decide the hosted deployment limits. The Phase 4 live gateway and browser checks are complete; hosted deployment remains outside the completed scope.
