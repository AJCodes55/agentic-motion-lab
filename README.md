# Agentic Motion Lab

A Citi Bike analytics demo for Jersey City. Upload or retrieve monthly trip data, generate verified reports, and use an agent to investigate monthly and station-level trends. The frontend uses Next.js; the backend uses FastAPI and Python for the calculations.

## About the project

This project explores how an AI agent can turn natural-language questions into reliable reports about bike-sharing activity. It helps users understand how trip volumes change between months, which stations gain or lose trips, and how rider types and bike types contribute to those changes.

Users load public Jersey City Citi Bike trip data and ask questions such as “Compare trip starts at HB107 in July 2026 with August 2026.” The application presents the results as summary cards, charts, and detailed breakdowns, with notes when the data is insufficient for a percentage or comparison.

The agent selects from a defined set of analytical tools; Python computes the figures and validates report claims against the underlying results. A separate baseline report runs without AI, providing a reference for evaluating the agent's output. The goal is to combine the flexibility of natural-language analysis with reproducible calculations and transparent evidence.

## Requirements

- Python 3.14 and Node.js 24 (the versions used for this project).
- Internet access to install dependencies and retrieve public Citi Bike data.
- An OpenAI-compatible API key for live model-assisted analysis. Baseline reports, supported queries, and the station comparison example below can run without a key.

Python packages are listed in `backend/requirements-dev.txt` and `backend/pyproject.toml`. Frontend packages are listed in `frontend/package.json`.

Commands below use a macOS/Linux terminal or Windows with WSL. Start from the repository root.

## 1. Set up the backend

```sh
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
python -m pip install --no-deps -e backend
```

For live agent analysis, create a local configuration file if you do not already have one:

```sh
cp backend/.env.example backend/.env
```

Edit `backend/.env` and replace the API key placeholder. Keep this file private. The application accepts the public OpenAI API or an OpenAI-compatible gateway URL.

## 2. Start the application

Keep both terminals running during the demo.

**Terminal 1 — backend**, from the repository root:

```sh
source backend/.venv/bin/activate
python -m uvicorn mobility.app:app --host 127.0.0.1 --port 8000 --env-file backend/.env
```

For a demo without an API key, omit `--env-file backend/.env`. The backend does not load that file automatically.

**Terminal 2 — frontend**, from the repository root:

```sh
cd frontend
npm ci
BACKEND_URL=http://127.0.0.1:8000 npm run dev
```

Open **http://localhost:3000**. Click **Check connection** and confirm **Backend connected**. API documentation is available at http://127.0.0.1:8000/docs.

## 3. Run the demo

### Load the data

1. Set **Reporting month** to **July 2026** and click **Fetch public Citi Bike data**.
2. Wait for an **accepted** result, then repeat for **August 2026**.
3. Confirm both months appear under **Available months**. Leave the reporting month set to **August 2026**.

Alternatively, download the Jersey City files from [Citi Bike system data](https://citibikenyc.com/system-data), choose them under **Select data**, and click **Upload selected files**. Upload one or two CSV/ZIP files at a time, up to 25 MB per file and 50 MB total. Keep filenames such as `JC-202607-citibike-tripdata.csv` or `JC-202607-citibike-tripdata.csv.zip` so the application can identify the month. Datasets are not included in this repository.

### Generate a station comparison

Enter this in **Analysis request**, then click **Run agent analysis**:

```text
Compare trip starts at HB107 in July 2026 with August 2026
```

The report shows station details, July and August trip totals, absolute change, and rider-type and bike-type breakdowns. Percentages may be withheld when the sample is too small; the report explains why. This supported comparison uses deterministic calculations and does not require an API key.

### Demonstrate the other report options

- **Monthly baseline:** keep August 2026 selected, go to **Baseline report**, and click **Generate baseline report**. This works without an API key.
- **Live agent:** with a valid API key configured, enter `Generate a standard monthly report for August 2026` and click **Run agent analysis**. Watch the four progress stages and review the generated report.
- **Report history:** click **Refresh report history** and open a saved report.
- **Baseline vs Agent (optional):** this separate comparison is fixed to January and February 2026. Load both months, select February 2026, click **Refresh demo months**, then **Run demo comparison**. A valid API key is needed for its live agent component.

## Troubleshooting

- **Backend unavailable:** confirm Terminal 1 is running on port 8000 and the frontend's `BACKEND_URL` matches it.
- **Missing month or station:** confirm the required datasets were accepted. Station comparisons need both months and a station present in those datasets.
- **Public data retrieval fails:** download the same Jersey City monthly file and use the upload option.
- **Agent unavailable or partial:** check the API key, gateway, and model in `backend/.env`, then restart the backend with `--env-file backend/.env`. Baseline reports remain available without a model key.

Accepted datasets and saved reports are stored in `backend/.local-data` and persist across restarts. Press **Ctrl+C** in both terminals to stop the application.

## Optional: run the tests

With the backend environment activated:

```sh
cd backend
python -m pytest
```

In another terminal, from the repository root:

```sh
cd frontend
npm test
```
