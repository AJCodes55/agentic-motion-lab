# Agentic Motion Lab

A Citi Bike reporting application for exploring monthly Jersey City trip data. A Next.js interface connects to a FastAPI backend for data ingestion, deterministic analytics, and bounded agent workflows.

## Features

- Import monthly Citi Bike CSV files or ZIP archives with schema and data-quality validation.
- Generate monthly KPI reports and compare adjacent months.
- Explore station rankings, station trip counts, and supported rider and bike-type breakdowns.
- Inspect agent progress, tool results, verified report figures, and request traces.
- Keep accepted datasets and report history in local storage.

The agent selects from a constrained set of analytical tools. Python computes the figures and validates report claims. Requests outside the supported monthly scope, including forecasting, causal explanations, weekly analyses, and median calculations, are refused. Each agent workflow allows at most six LLM calls and ten tool calls.

## Local setup

Use Python 3.11 or newer and Node.js 24. Run commands from the repository root unless indicated otherwise.

### Backend

```sh
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
python -m pip install --no-deps -e backend
python -m uvicorn mobility.app:app --host 127.0.0.1 --port 8000
```

For model-assisted planning, set these environment variables before starting the backend:

```sh
export OPENAI_API_KEY='your-api-key'
export OPENAI_BASE_URL='https://api.openai.com/v1'
export OPENAI_MODEL='gpt-5-nano'
```

The backend also supports `https://api.portkey.ai/v1`; use a model identifier available through your gateway. Model-assisted requests can send aggregate analytical context to the configured provider. Deterministic reporting does not require a model key. Keep credentials out of source control.

### Frontend

In a separate terminal:

```sh
cd frontend
npm ci
BACKEND_URL=http://127.0.0.1:8000 npm run dev
```

Open http://localhost:3000. Backend API documentation is available at http://127.0.0.1:8000/docs.

## Data and usage

Obtain Jersey City monthly files from [Citi Bike system data](https://citibikenyc.com/system-data) and import them through the application. Use the expected `JC-YYYYMM-citibike-tripdata.csv` naming convention. Load adjacent months to enable comparisons, then select the reporting month.

Example requests:

- `Generate the May 2026 report and investigate any qualifying station decline.`
- `Compare trips started at HB506 in May 2026 with April 2026`

These examples require the corresponding months to be loaded. A station absent from the accepted data produces a station-not-found response. Import validation and cleaning can make accepted trip totals differ from raw file totals.

Local datasets default to `backend/.local-data`; configure `MOBILITY_DATA_ROOT` to use another location. This repository contains application source and tests. Raw datasets, private evaluation results, human scores, planning documents, and local assistant configuration are excluded.

## Checks

```sh
cd backend
python -m pytest
```

With the backend environment activated, run frontend checks in another terminal:

```sh
cd frontend
npm run typecheck
npm run lint
npm run test:coverage
npm run build
npx playwright install chromium
PYTHON=../backend/.venv/bin/python npm run test:e2e
```

GitHub Actions runs backend coverage, API contract checks, frontend checks, and browser tests.

## Repository layout

- `backend/src/mobility/`: API, ingestion, analytics, agent tools, validation, and storage.
- `backend/tests/`: backend regression and integration tests.
- `frontend/`: application interface, API proxies, component tests, and browser tests.
- `contracts/openapi.json`: shared API contract snapshot.

This application uses local filesystem storage. A deployment must provide suitable persistent storage and access controls for its intended environment.
