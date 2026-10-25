# Phase 1: Local Application Foundation

Current application behavior now includes [Phase 2 ingestion and storage](phase-2.md). This document preserves the original Phase 1 scope and setup; upload controls are now functional as described in Phase 2.

This phase establishes a Next.js/Tailwind interface and FastAPI service. It does not ingest files, run analytics, call an LLM, or generate reports. Source verification and reference expectations remain in [Phase 0](phase-0/dataset-manifest.md).

## Local Setup

Use Python 3.14 and Node.js 24 or newer. Run commands from the indicated directory. Dependency installation requires network access.

From `backend/`:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps -e .
PYTHONPATH=src MOBILITY_DATA_ROOT="$PWD/.local-data" .venv/bin/python -m uvicorn mobility.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal, from `frontend/`:

```sh
npm ci
npm run dev -- --hostname 127.0.0.1
```

Open `http://127.0.0.1:3000`. The frontend server connects to the backend through its own `/api/health` route; browser requests do not require cross-origin backend access. The backend URL defaults to `http://127.0.0.1:8000`. Override `BACKEND_URL` in the frontend process environment when needed. Never place private credentials in `NEXT_PUBLIC_*` variables. No API key is required in this phase.

Stop the backend and retry the connection in the interface to see the unavailable-service state. Restart the backend and retry to recover. Upload and report controls explain that their processing is not yet implemented; a connected service does not imply report readiness.

## Checks

From `backend/`:

```sh
.venv/bin/python -m pytest
```

From `frontend/`:

```sh
npm run typecheck
npm run lint
npm run test:coverage
npm run build
npx playwright install chromium
npm run test:e2e
```

Coverage thresholds apply to the implemented behavior, not future analytical features. Browser tests start their own local services; close servers on their configured test ports first.

## Shared Contracts

Backend Pydantic declarations are the source of truth. To refresh the OpenAPI snapshot from the workspace root:

```sh
backend/.venv/bin/python -m mobility.export_openapi > contracts/openapi.json
```

Then run `npm run contracts:generate` from `frontend/`. The generated TypeScript is checked in; do not edit it manually. CI checks schema/type drift, backend tests, frontend checks, build, and browser behavior. The workflow is prepared locally; remote CI execution is not implied.

Request IDs link safe API errors to structured service logs. Logs must omit raw trip rows, request bodies, secrets, and private model reasoning. Use `--no-access-log` as shown: default server access logs include unredacted request paths and query strings. The application emits its own structured request logs using route templates. Request IDs identify HTTP requests; analytical run IDs are separate contract fields for later phases.

## Deployment Boundary

These commands start local development services. Hosted authentication, isolation, capacity, byte/expansion limits, recovery, and retention semantics remain explicitly deferred. Resolve them before exposing the relevant application functionality. No deployment is performed by this phase.

## Dependency Review

On 2026-10-18, `npm audit --omit=dev` reported zero vulnerabilities. The full audit reported five HIGH entries propagated from one unresolved development-tool dependency advisory, [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), through ESLint's glob dependencies. Security review found no application-input path to this glob parser in Phase 1. Crafted patterns in untrusted lint configuration can exhaust the lint process stack. Keep lint configuration trusted and recheck for a compatible upstream patch; the full dependency audit is not clean. No forced framework downgrade was applied.

## Local Verification — 2026-10-18

| Check | Result |
| --- | --- |
| Backend unit/integration tests | 17 passed; 99.33% statement coverage |
| Frontend unit/integration tests | 11 passed; 100% line/function/statement coverage; 90.9% branch coverage |
| Browser tests | 2 passed: outage/retry UI and live browser → frontend proxy → FastAPI connection with request ID |
| Frontend lint and TypeScript | Passed |
| Production build | Passed using supported webpack mode |
| Contract snapshot and generated types | Refreshed from final backend definitions; schema references resolve |
| Reviews | Python, React, TypeScript, general code, and scoped security reviews completed; no blocking code findings |
| Dependency checks | Production npm audit clean; development advisory documented above |

Turbopack's CSS IPC was blocked by the execution environment. The `dev` and `build` scripts explicitly select webpack, which successfully builds this application. Browser tests use the matching full Chromium browser. The outage browser test simulates an unavailable response; the second test uses the actual running backend through the proxy. These are foundation checks, not execution of the 44 Phase 0 analytical and ingestion specifications. Following initial publication, [GitHub CI](https://github.com/AJCodes55/agentic-motion-lab/actions/runs/39163539007) started; it was still running at this documentation update.

Tests were authored before implementation; initial baseline runs were blocked by missing dependencies, so a full initial red/green cycle is not claimed. The final logging/year-bound fix has demonstrated failing and passing regression checks. No production upload endpoint, dataset activation, grounded report, or hosted release is represented as verified here.

## Dependency Audit Refresh — 2026-10-24

Before the authorized Phase 6 commit/push, both `npm audit --omit=dev` and full `npm audit` reported zero known vulnerabilities. Python's pinned requirements audit covered 31 packages with no known vulnerabilities. No dependency versions were changed for this publication. Earlier nonzero development audit results above remain historical observations, not the current audit result.
