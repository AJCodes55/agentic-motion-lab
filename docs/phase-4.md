# Phase 4 — Agentic MVP and Grounding

Status: implemented and verified locally with both an injected deterministic model and a live request through the university gateway. This is not a production-readiness claim.

## Behavior

The agent starts from the Phase 3 fixed baseline and uses its pinned dataset references for every selected aggregate tool. It classifies the request, checks available periods, selects approved analysis tool names, runs aggregate tools, selects the mandatory qualifying station-mover candidate, and requests a station variance follow-up for the pinned current and prior months. Python binds all period and tool arguments; the model chooses only the follow-up station. Successful follow-up must provide both member/casual and rideable-type contributions. A final strict structured draft can select only exact candidate claims built from successful aggregate evidence; Python validates evidence identity and renders approved claim templates. The model cannot run arbitrary code or supply report HTML.

The state machine caps a run at six model calls and ten selected tool calls. It permits one bounded retry for plan/result and claim gates. A failed, wrong-station, wrong-month, incomplete, or ungrounded result cannot enter the final narrative. A failure or missing provider credentials yields the deterministic baseline with a pass-with-limitations warning. Unsupported requests are refused with a supported alternative. Per-run counters, tool trace, stage status, failure code/reason, and rendered artifact are archived under the baseline report ID.

The interface streams four stage statuses, the chosen candidate, and validated aggregate activity. The final report is displayed in a sandboxed iframe. The frontend proxy limits request bytes and forwards only to a server-controlled backend origin. The backend reads `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` from its environment. The university configuration uses the OpenAI-compatible Portkey gateway and its `@30875-fall26-openai/gpt-5-nano` route. No separate Portkey provider slug was supplied or is required by the assignment example.

## Verification

- Backend: 156 tests passed with 94.56% coverage. Tests include request routing, strict schemas, invalid plans, retries, budgets, pinned replacement snapshots, forged/wrong evidence, incomplete variance, fallback, and stream API behavior.
- Frontend: 45 tests passed; 95.44% statement, 82.25% branch, 92.06% function, and 98.37% line coverage. Typecheck, lint, and production build passed.
- Browser: four Playwright tests passed, including the streamed agent request and visible adaptive variance follow-up.
- Real January/February cached source files were ingested into a temporary store and run through the full agent state machine using an injected deterministic model. The run selected `HB106`: 1,584 prior starts, 866 current starts, change −718. Both variance breakdowns, grounded Member wording, and matching archived artifacts were verified. Machine-readable result: [mock real-data check](phase-4-mock-real-data.json).
- A live run against the university gateway used the same verified public January/February data. It completed with candidate `HB106`, three successful tool calls (available periods, station movers, station variance), four model calls, both variance dimensions, grounded Member wording, and matching archived HTML. Usage counters recorded 3,740 input and 413 output tokens. [Live real-data check](phase-4-live-real-data.json) contains no credential or raw trip rows.
- On 2026-10-22, the four browser tests passed sequentially on isolated local ports. A separate browser check used the real frontend, backend, configured university gateway, and already ingested data; it displayed candidate `HB106`, the variance follow-up, and Member wording in the rendered report. The first concurrent browser-suite run had one ingestion UI timing failure; that test passed alone and in the full sequential rerun. The live browser check was temporary and is not part of the credential-free automated suite.

## Local university gateway configuration

Copy `backend/.env.example` to `backend/.env` and replace only the key placeholder with the university-provided key. Keep the provided `OPENAI_BASE_URL` and `OPENAI_MODEL` values. From the `backend` directory, launch or restart with:

```bash
.venv/bin/python -m uvicorn mobility.app:app --host 127.0.0.1 --port 8000 --no-access-log --env-file .env
```

The file is Git-ignored. No separate Portkey provider slug is required by the assignment configuration. Do not paste the key into chat.

## Remaining limits

The university key was rejected by the public OpenAI endpoint with HTTP 401, then worked through the university Portkey gateway and model route. Earlier live attempts correctly returned baseline-only fallback when the provider response exhausted its output budget or failed validation; the successful run followed bounded plan, evidence, and claim constraints. The provider returned token counts but no monetary cost. A streamed client disconnect still does not cancel an already-running model workflow; cancellation and hosted request limits should be addressed before deployment. Production access controls, retention, hosted capacity, and recovery remain later decisions under the SRS.
