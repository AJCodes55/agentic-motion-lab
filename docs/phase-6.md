# Phase 6 — Interface polish and operational hardening

Current status: local interface and D26–D29 operational tooling are verified; manual operation and deferred hosted requirements remain. Initial local scope was authorized under D20–D21 on 2026-10-22. Local verification does not establish hosted production readiness. Hosting remains future work; eventual 100+ user access requires architecture, isolation, workload and capacity verification. Hosted operational policies are explicitly deferred; see the remaining-work table in the implementation plan.

## Initial offline integrity and recovery foundation — historical checkpoint

Run from `backend/` with the service and all writers stopped:

```sh
.venv/bin/python -m mobility.operations /absolute/path/to/data-root > /tmp/mobility-before.json
```

The inspector opens the existing registry read-only, checks SQLite integrity and foreign keys, checks active pointer periods, verifies every registered version's CSV checksum and metadata/KPI identity, and recomputes monthly metrics. It prints SHA-256 hashes for all files, inventories inactive registered versions and unregistered directories, and exits nonzero on detected problems. It does not create a missing root, activate versions, repair files, or delete data. Symlinks and nonempty SQLite journal/WAL sidecars fail inspection. This is an **offline** tool; it neither locks out running writers nor guarantees a consistent live snapshot.

Local rehearsal procedure:

1. Stop the backend and any CLI/test processes using the same data root. Keep frontend traffic away until verification finishes. Confirm no ingestion or report write is running; the ingestion lock alone does not cover report writers.
2. Run inspection and retain its JSON outside the data root. Investigate failures before treating a copy as valid. Do not remove SQLite sidecars manually; ensure writers have cleanly closed their databases first.
3. Copy the **entire** data root to a new directory on local storage, preserving file contents and directory structure. Include registry, every dataset version, report/evidence/chart/agent artifacts, quarantine and rejection records. Copying only active CSV/KPI files loses archived provenance. Do not copy the backend `.env` into a data backup.
4. Inspect the copy. Compare the complete JSON (including every relative file checksum) with the source inspection; any difference needs investigation. A checksum manifest detects differences relative to a trusted original; it does not authenticate a compromised backup.
5. Rehearse recovery into a second new, isolated directory. Inspect again and compare manifests before starting an isolated backend with `MOBILITY_DATA_ROOT` set to that directory. Verify active periods and open representative saved reports; do not ingest or request a new agent run just to validate saved artifacts. Avoid generating provider calls during the rehearsal.
6. For an actual local recovery, preserve the failed root and use a separately verified restored root. Restart with its explicit data-root configuration only after operational approval for the incident. Never overwrite the only surviving copy or silently rebuild saved reports from newer datasets.

Automated tests rehearse full-directory copy/inspection equivalence with active, inactive and interrupted versions, corruption/dangling pointers, missing roots and symlink refusal. This verifies local mechanics on a small synthetic fixture, not disaster recovery at deployment scale. File hashes cover saved reports, traces, evidence and quarantine bytes, but this inspector does not semantically validate every archived report or source manifest; manual saved-report checks remain part of the rehearsal.

At the initial checkpoint, no orphan deletion was implemented; D26–D29 and the operational completion below supersede that limit. Inactive registered versions may be required by archived reports, and an unregistered directory may contain interrupted evidence. Neither category is proof that deletion is safe. Retention clock, artifact coverage, archive-expiry behavior and backup lifecycle need decisions before cleanup can be specified.

## Verified existing boundaries and unresolved operations

Approved local limits remain 25 MB/file, 50 MB file bytes/request, 200 MB expanded CSV, 100 CSV members, one ingestion at a time, and a 30-second incoming body deadline. Ingestion uses a process lock and a nonblocking `flock` on the same local data root. This is not a distributed queue or a portable cross-host concurrency guarantee. Report/model request concurrency and aggregate memory/cost are not globally bounded by that ingestion lock. SQLite activation preserves pinned immutable versions; tests cover interruptions around activation and snapshots across concurrent replacement.

The application remains a local, unauthenticated service. Local retention/recovery policy portions were subsequently resolved by D26–D29 below. Hosting provider/storage topology, identity and per-user authorization/isolation, hosted request/model concurrency and quotas, retention start clock and artifact coverage, backup destination/frequency/encryption/access/lifecycle, and recovery RPO/RTO and ownership remain unresolved. No hosted exposure, scheduled backup, automated restore/failover, destructive expiration, remote storage or production readiness claim is introduced by this phase.

## Local latency and cost observation

On 2026-10-22, five sequential baseline generations took 1134.58, 1176.17, 1147.78, 1130.90 and 1127.43 ms (median 1134.58 ms). This isolated local synthetic fixture used 100 stations, 39,198 prior and 25,387 current rows, all on day 1 with Member/Classic categories. Setup/ingestion was excluded; report calculation, rendering and durable archive writes were included. This is a narrow local observation, not a hosted capacity, realistic distribution or latency guarantee. No new model request or paid gateway call was made for this measurement.

The baseline uses zero LLM calls. Existing request logs record `duration_ms`; saved agent records track calls and available token usage. The earlier verified live gateway run used four model calls, three successful tool calls, 3,740 input tokens and 413 output tokens (see Phase 4). A dollar cost cannot be derived without verified university gateway pricing. No price, cost target or hosting latency target is assumed. No optimization is justified by this small sample; hosted profiling and representative mixed-data workloads remain needed.

## Operations verification

Focused backend verification on 2026-10-22: **69 passed** across operations, storage, ingestion, and ingestion API tests. Ten new offline operations tests cover missing roots/registries without creation, copy/restore checksum equivalence, preserved inactive/interrupted versions, CSV corruption and dangling active pointers, wrong-period pointers, unchanged file bytes after inspection, unsettled SQLite sidecars, malformed metadata, symlink refusal and nonregular registry refusal. The first new-test run failed because the operations module did not exist (RED); implementation and review fixes made the tests pass. One existing Starlette/httpx deprecation warning remains. Later full-suite and interface verification is recorded below.

## Interface and report changes

The workspace now has a keyboard skip link, section navigation, visible focus and narrow-screen controls with wrapping. Available months distinguish loading from truly empty data and offer retry on failure. Upload quality separates exclusions from retained Unknown classifications and preserves rejected-upload explanations. Tool activity uses readable names, explicit station/month context and expandable exact tool inputs, while exposing validated aggregates only. Progress and completion have live status announcements; the baseline viewer hides reports and errors from a different selected month. Existing no-context request rules, explicit station choices, sandboxed frames, grounding and fallback logic remain intact.

Newly generated baseline and ad-hoc reports share responsive/print styles, semantic column headers and keyboard-scrollable tables/charts. Daily and every monthly mix chart have adjacent data tables. Solid/dashed daily series and matching legends supplement color. Original saved archives are not rewritten.

## Final verified results — 2026-10-22

| Check | Result |
| --- | --- |
| Backend full suite | 214 passed; 94.14% statement coverage. Ten operations tests include malformed registry diagnostics and full archived-report restore after active-version replacement. |
| Frontend full suite | 68 passed; 95.86% statements, 84.95% branches, 94.62% functions and 98.78% lines. |
| Browser and build | 8/8 Chromium tests passed against a production frontend build on isolated loopback ports. Includes real upload/replacement/rejection, station choice/chart/archive flow, adaptive activity, outage/retry, mobile skip-link focus and keyboard horizontal scrolling. |
| Static/contracts | Frontend lint/typecheck passed; exported OpenAPI matches the committed contract snapshot; diff whitespace check passed. |
| Reviews | Python/security, React, TypeScript/general code and accessibility reviews completed. Blocking findings were addressed, including malformed recovery inputs and nonvisual chart values. |

The final backend suite retains one Starlette/httpx deprecation warning. Python static-analysis tools were unavailable; no static-Python pass is claimed. Browser checks cover Chromium at desktop and a 375px viewport, not full WCAG conformance or assistive-technology testing. No new live model/gateway verification, dollar-cost calculation, hosted load test or disaster recovery at scale was performed. The recovery fixture proves saved baseline HTML/evidence identity after copying, not semantic validation of every possible archived agent/ad-hoc artifact. Local UI work and recovery foundations are verified; deferred Phase 6 deployment work remains listed in the implementation plan. No commit, push or deployment was performed.

## Vercel Services preparation — 2026-10-24

The user requested Vercel configuration, then explicitly chose **configuration only for now; durable backend storage is the next decision**. This authorizes local preparation, not a working hosted release. The proposed service names, public routing and binding still require the user's requested final confirmation.

Root `vercel.json` proposes `frontend` (Next.js) as the only publicly routed service at `/(.*)`, including the existing `/api/*` Next.js route handlers. `backend` (FastAPI) stays internal. The caller `frontend` declares a service binding to `backend` as `BACKEND_URL`. Vercel generates this value at runtime; do not set it in project environment variables. Existing local launch commands may still explicitly set `BACKEND_URL` for localhost testing.

Request flow is browser `/api/reports` → frontend function → bound backend `/reports`. The same pattern covers health, ingestion, supported queries, history and agent streaming. Routing `/api/*` directly to the backend would bypass existing proxy validation, body/response bounds and safe error handling; Vercel service rewrites also preserve the matched path prefix, while FastAPI currently has unprefixed routes. No backend public rewrite or new ASGI prefix is introduced.

The URL resolver reads the binding inside request handlers, preserves a base path if supplied, and fails safely on Vercel if the binding is missing. It retains the localhost default for ordinary local development. No binding lookup occurs during build or middleware execution. The backend entrypoint `src.mobility.app:app` resolves the actual source file relative to the service root. Its install command installs the package (`python -m pip install .`) so existing absolute `mobility.*` imports work without source-path hacks. `backend/.python-version` selects Python 3.14, matching the existing CI/test version. `.vercelignore` excludes credentials, local datasets/state and generated caches; `.vercel/` project metadata is ignored by Git.

### Local services rehearsal

After installing a current Vercel CLI with Services support, run from the repository root:

```sh
vercel dev --local
```

`vercel dev` also runs the services and injects the bindings; `--local` avoids cloud authentication. The requested `vercel dev -L` works but CLI 65.2.0 reports that `-L` is deprecated in favor of `--local`. Use an isolated local data root (`MOBILITY_DATA_ROOT`) for this rehearsal rather than the only copy of existing evidence. Never manually define the binding in Vercel. The ordinary FastAPI/Next.js launch commands remain supported. A passing standalone Next.js build does not validate Vercel's service builder or private networking.

### Gates before actual deployment

1. **Durable state:** the current backend initializes a writable local SQLite registry at import and stores CSV/KPI versions, evidence and archived reports on disk. Vercel Functions cannot supply durable shared local SQLite storage. Decide and implement shared durable database/artifact storage, preserve pinned version identity, and test replacement/concurrency/recovery. Pointing the application at `/tmp` would lose state and is not an approved substitute.
2. **Upload transport:** approved 25 MB/file and 50 MB/request exceed Vercel Functions' 4.5 MB request-body limit. Decide a direct object-storage upload/validated ingestion design, or explicitly approve changed hosted limits. Server-side public-source fetching avoids sending the archive in a browser request but does not solve persistence, memory, time or concurrency limits.
3. **Access and capacity:** choose deployment protection/authentication and shared versus per-user data/report permissions before exposing mutable data and provider calls. An internal backend does not protect the public frontend API from unauthorized users. Bindings grant reachability, not application authorization. Define quotas, durations and workload tests; the future 100+ user goal remains unverified.
4. **Recovery/retention/secrets:** approve the existing deferred retention and backup/recovery policies for the selected durable services. Supply the provider key only through server-side secrets; do not assume a shared Vercel environment isolates it to one service. Review runtime duration, streaming and package-size limits against the selected plan before publishing.

References: [Services](https://vercel.com/docs/services), [service routing](https://vercel.com/docs/services/routing), [bindings](https://vercel.com/docs/services/bindings), [FastAPI entrypoints](https://vercel.com/docs/frameworks/backend/fastapi), [Python runtime](https://vercel.com/docs/functions/runtimes/python), [SQLite limitations](https://vercel.com/kb/guide/is-sqlite-supported-in-vercel), [Function limits](https://vercel.com/docs/functions/limitations).

### Vercel preparation verification — 2026-10-24

- Frontend: 75 tests passed, including seven new binding regressions covering all three proxy callers, changed bindings after import, base-path preservation, safe missing-binding errors on Vercel, and local fallback. Lint/typecheck and the production build passed without binding availability at build time. Reported suite coverage retains its existing include scope; the new helper is verified through caller tests, not included in that coverage percentage.
- Vercel CLI 65.2.0 detected both services and ran `vercel dev -L --listen 3147` with an isolated temporary data root. `/api/health` returned 200 from the bound backend, `/api/periods` returned 200 with an empty isolated store, and `/health` returned frontend 404. No dataset/model request was made. The local server was stopped after checks. No Vercel account/project was linked and no deployment was triggered.
- The configuration matched the published Vercel JSON schema's constraints using the installed Ajv validator. Schema self-validation had to be disabled because the published draft-04 schema contains newer numeric `exclusiveMinimum` keywords in unrelated function-trigger definitions. CLI service detection and actual local routing provide the additional checks; a cloud service build remains unverified.
- TypeScript/general/security review found no blocking issues in the configuration and proxy changes. Existing uncommitted Phase 6 work was preserved. Backend application behavior was not changed and no new backend full-suite pass is claimed for this preparation step.

The user approved service names, public exposure/paths and caller-to-target binding under D23. D25 subsequently deferred deployment to the final stage. Deployability remains gated on durable state, upload transport and access controls. No commit, push or deployment.

## Deployment handoff deferred — 2026-10-24

D25 makes local development and evaluation the active scope. Render credits are pending activation; revisit hosted deployment after Phase 7 when the user requests it. No hosting purchase, migration or deployment is underway. Keep the Vercel preparation and local verification above; Render was recommended but is not yet configured or selected as an approved paid plan. The authoritative return checklist is the **Final Deployment Stage — After Phase 7** in [the implementation plan](../implementation_plan.md). Local SQLite and existing application behavior remain unchanged; hosted persistence, upload, access, capacity, retention and recovery gates still require resolution before exposure.

## Local operational implementation — D26–D29, 2026-10-24

The earlier local completion statement covered interface polish and recovery foundations only. The following operational tooling is now implemented and verified; hosted setup remains deferred under D25. No cleanup or backup was run against existing project data during development; all destructive tests used isolated fixtures.

### Retention behavior

`registry.sqlite` now holds upload timestamps separately from immutable metadata/evidence. New accepted versions and rejection records share one UTC timestamp captured at ingestion start. January 2026 data uploaded on October 24, 2026 expires April 24, 2027 at the corresponding UTC time. Six calendar months are used, not 180 days; invalid month-end dates clamp to the final day of the target month. Reuploads get separate clocks; reading, activating, generating reports and restoring backups do not restart old clocks.

Expired versions disappear from available periods and cannot be read for new reports. Saved report history is also gated by the complete baseline dataset dependency set; its earliest-expiring version determines report expiry even if an ad-hoc final result uses fewer versions. Physical cleanup removes the entire expired report directory (baseline/agent/ad-hoc HTML, charts, evidence, traces), dataset directory (CSV/KPI/metadata) and relevant registry entries. No older version is silently reactivated. Shared rejected-upload quarantine bytes are retained until all related rejection records expire.

**Legacy uploads without clocks stay untouched** under D29. Unknown/incomplete directories and staging artifacts are inventoried, not automatically deleted. Original upload dates must be supplied before these can become cleanup candidates; filesystem dates are not substitutes. Read denial happens automatically at expiry, but physical cleanup and managed-backup pruning are explicitly invoked offline operations, not a background scheduler. No claim of exact-time physical erasure is made.

### Cleanup procedure

Stop every backend process, ingestion script, report writer and other maintenance process using the root. The current app holds a shared root lock for its lifetime; maintenance takes an exclusive lock and refuses while that app is serving. This is cooperative local locking: older running code or scripts bypassing the lock still require explicit shutdown.

From `backend/`, using the actual canonical data-root path:

```sh
.venv/bin/python -m mobility.retention /absolute/data-root
```

This is a dry run. It reports expired versions, dependent reports/rejections/quarantine and blocked legacy/unknown artifacts. Review it and make a verified backup while the data is still eligible for backup, before risky changes. Backups containing already expired data are refused; an expired snapshot cannot be used to bypass retention.

```sh
.venv/bin/python -m mobility.retention /absolute/data-root --apply
```

`--apply` explicitly opts into deletion and recomputes the plan; the Python API also accepts a reviewed plan and refuses it if its fingerprint/contents changed. A checksum-protected, flushed journal is written before registry/file changes. If interrupted, the serving app refuses startup until offline recovery finishes:

```sh
.venv/bin/python -m mobility.retention /absolute/data-root --recover
```

Recovery validates paths, dates and dependency closure and resumes idempotently. Corrupt journals, unsafe paths/symlinks or inconsistent evidence fail closed. Checksums detect accidental corruption, not malicious rewrites by an actor with full data-root write access.

### Backup and restore procedure

Use a separate, explicit backup location outside the source data root and preferably outside the repository/on a separate device. Canonical absolute paths are required; symlink path components are refused. Same-disk copies do not protect against disk or laptop loss. No backup location, cloud resource, unattended scheduler or spending is configured implicitly.

```sh
.venv/bin/python -m mobility.backups create /absolute/data-root /separate-volume/mobility-backups
```

The command returns a `snapshot-...` directory. It validates data and report identities, copies all data/evidence, flushes files/directories and publishes a manifest with checksums, creation time, legacy inventory and absolute expiry. Root lock files are excluded because copying them cannot transfer lock ownership. Secret-like or unrecognized root files are refused for review.

```sh
.venv/bin/python -m mobility.backups restore /separate-volume/mobility-backups/snapshot-ID /absolute/new-restored-root
```

The destination must not already exist and must not overlap the backup. Restore validates inventory, hashes, dataset/report evidence and original retention. Expired snapshots are refused. It reports backup age and restore duration against the 24-hour RPO/one-hour RTO targets. A process/power interruption can leave a partial new destination; keep the original snapshot and retry into another new directory. Never overwrite the only surviving copy. Replication to another device, disaster recovery and power-loss behavior have not been verified by these tests.

Managed snapshots expire as a whole at their earliest known artifact expiry. Prune first lists candidates; apply is explicit:

```sh
.venv/bin/python -m mobility.backups prune /separate-volume/mobility-backups
.venv/bin/python -m mobility.backups prune /separate-volume/mobility-backups --apply
```

Pruning an expired mixed snapshot also removes legacy backup copies inside it; the output explicitly lists these. It does not delete working legacy uploads. Keep separate legacy recovery copies if needed. Unknown/unmanaged folders are not automatically pruned; arbitrary external copies cannot be expired by this tool.

Back up before risky changes and after important demo preparation as approved. During ongoing changes, also create a backup at least daily to meet the intended 24-hour freshness target. Event-triggered backups alone cannot guarantee RPO, and no scheduler is installed. The operator owns local execution and must select/manage storage; hosted scheduling, access/encryption and recovery ownership remain deployment decisions.

### Verification and measured recovery

Backend full suite: **254 passed, 93.14% statement coverage**. New coverage includes calendar/month-end and exact expiry boundaries; shared batch clocks; preserved legacy artifacts; dataset/history API denial at expiry; dry-run/stale-plan protection; rejection/quarantine references; corrupted evidence/journal and unsafe paths; interrupted deletion/recovery; active app/maintenance exclusion; backup/restore corruption, destination conflicts, partial copy/flush failures, snapshot expiry/pruning and stale-backup RPO flags. One existing Starlette/httpx deprecation warning remains.

A separate local synthetic rehearsal used 64,585 cleaned rows across two months/100 stations with a baseline HTML/SVG/evidence archive (4,141,517 source bytes). Backup took **2.180 seconds**; verified restore took **2.169 seconds**. The fresh backup age was about **0.012 seconds**. This observation met the one-hour RTO and 24-hour freshness thresholds for this fixture only. It does not prove recovery of a real disk failure, the full range of agent/ad-hoc archives, deployed scale or an ongoing RPO guarantee. No provider calls were made.

Python/general/security reviews found no blocking findings within trusted, cooperative offline scope. All eight browser checks passed with a production frontend build after the shared-store harness was serialized. The first parallel run had seven passes and one ingestion-busy failure: the screenshot showed the approved single-ingestion lock working. The test harness now uses one worker; application concurrency behavior was preserved. Typecheck/lint, contract snapshot and diff checks pass. Test servers were stopped. Final general code review also approved the changes with no blocking findings. The API contract snapshot is unchanged. No hosted deployment, real-data deletion, commit or push occurred.

### Selected local backup location — D30

The user selected `~/Main drive/agentic-motion-lab backup` as the parent for managed `snapshot-...` backups. It is outside the repository/default working data root, without symlink components. The corrected folder already exists. Its parent is on the same filesystem as the working data, so it is a useful local recovery copy but not independent protection against disk/machine loss. No backup was created by this path check. The backup command can create the parent directory when run with the needed filesystem permission and all writers stopped.

## First working-data backup and restore rehearsal — 2026-10-24

The user authorized continuing local operations with the existing `~/Main drive/agentic-motion-lab backup` directory. The identified project backend was gracefully stopped; port 8000 was confirmed closed before backup. The running service on port 3000 belongs to a separate portfolio project and was left untouched.

- Working source: repository `backend/.local-data`, two registered active versions, January 2026 (39,198 trips) and February 2026 (25,387 trips).
- Backup: `~/Main drive/agentic-motion-lab backup/snapshot-958958f96a73427bb48d261092b7d85f`.
- Verified isolated restore: `~/Main drive/agentic-motion-lab backup/restore-check-20261024T212550Z-6614757a`. Both backup and restored directory remain available; neither overwrote the working source.
- 128 application files, 18,247,807 bytes were backed up (the two advisory lock files are excluded). All data checksums and dataset integrity checks passed. All 13 saved report entries were read and validated, including their saved HTML/evidence identities. Restored monthly trip counts match the working store.
- Backup duration: 2.456 seconds. Restore duration: 2.425 seconds. Backup age at restore start: 0.064 seconds. This actual local rehearsal met the one-hour timing and 24-hour freshness thresholds; it does not establish ongoing RPO or recovery after device/filesystem loss.

The source application-file inventory was unchanged across backup/restore verification. Cleanup was **dry run only**: zero versions, reports, rejections or quarantine directories eligible for deletion; four entries were blocked due to unknown legacy upload dates. Both dataset versions remain undated under D29, so the managed snapshot has no inferred expiry. No dates were guessed, no retention clock was restarted and no data was deleted. Backup pruning and unattended scheduling were not run.

The backend was restarted using current repository source and the explicit working data root. An initial restart using the installed package selected its empty package-relative default; it was stopped and corrected. The installed-package default is not the working store. The corrected local service returned HTTP 200 for health, both active periods and all 13 history entries. The source registry's normal compatibility initialization added the empty retention table; no legacy timestamps were assigned. To reproduce this launch from `backend/`:

```sh
PYTHONPATH=src MOBILITY_DATA_ROOT="$PWD/.local-data" .venv/bin/python -m uvicorn mobility.app:app --host 127.0.0.1 --port 8000 --no-access-log --env-file .env
```

A managed local backend session is listening on `127.0.0.1:8000`; availability depends on that process remaining active. No provider call, source-code modification, commit, push or deployment was performed. Backup and restore copies share the working filesystem and do not provide independent disk-loss protection. The snapshot is application data/evidence, not a backup of source code, the virtual environment or credentials.

### Current project preview — 2026-10-24

Open `http://127.0.0.1:3001` for the interface. Port 8000 serves the API, not the project UI; port 3000 belongs to a separate portfolio. The current frontend was started from `frontend/` with:

```sh
BACKEND_URL=http://127.0.0.1:8000 npm run dev -- --hostname 127.0.0.1 --port 3001
```

Interface HTTP 200, backend health through the frontend proxy and both working periods were verified. Both local server processes must remain active.
