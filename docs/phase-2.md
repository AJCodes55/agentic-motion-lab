# Phase 2: Ingestion, Cleaning and Safe Storage

Status: complete for local development on 2026-10-18. Hosted authentication, capacity, retention enforcement and recovery operations remain gated before deployment. Phase 3 reporting and agent behavior are not implemented.

## Try It

Start both services using the [local setup commands](phase-1.md#local-setup), then open `http://127.0.0.1:3000`.

1. Choose one or two canonical Jersey City CSV/ZIP files and select **Upload selected files**. January and February may be uploaded together.
2. Alternatively, choose a reporting month explicitly and select **Fetch public Citi Bike data**. The backend constructs the official source URL; arbitrary URLs are not accepted.
3. Inspect accepted/rejected month results, source coverage, sequential exclusions, Unknown counts, threshold denominators and available versions.
4. Upload a corrected month. A successful correction creates a new version; a rejected correction preserves the previous active version.

Report generation remains disabled until the reporting phase. Available-month refresh errors are separate from ingestion results.

## Approved Limits and Batch Behavior

| Limit | Local value |
| --- | --- |
| Uploaded files | One or two |
| File bytes | 25,000,000 per file; 50,000,000 total |
| Expanded CSV data | 200,000,000 bytes across the request |
| CSV members | At most 100 across the request |
| Concurrent ingestions | One; process and filesystem locks enforce this |
| Incoming request body deadline | 30 seconds; timeout releases the ingestion lock |

The multipart transport has a small, separately bounded allowance for framing. File-byte limits remain authoritative. Request-global resource excess rejects the request before activation. Within an admissible request, months are validated and activated independently: a valid month may activate while another is rejected. Unsupported members are rejected within their month. They do not count as CSV members in the shared budget.

Canonical formats are `JC-YYYYMM-citibike-tripdata.csv`, `JC-YYYYMM-citibike-tripdata.zip`, and `JC-YYYYMM-citibike-tripdata.csv.zip`. Files and CSV members are processed alphabetically; row order is preserved. macOS metadata is ignored. Unsafe paths, symlinks, encrypted ZIP members, unsupported files, mismatched archive months and malformed schemas are rejected. ZIP contents are read without extracting user paths.

## Cleaning and Quality Accounting

The pipeline applies the SRS order: invalid timestamps, month tolerance, exact ride-ID deduplication, missing stations, duration bounds, category normalization, final empty check. Time boundaries use `America/New_York`. Threshold comparisons use integer counts without display rounding. Station identifiers remain strings, including literal values such as `NA`, `NULL`, and `None`; blank/whitespace and NaN markers are missing.

Accepted summaries reconcile `source_rows = valid_rows + excluded_rows`. On rejection, `valid_rows` is zero and `candidate_rows` records rows not yet excluded or accepted: `source_rows = excluded_rows + candidate_rows`. Stage, reason and denominators remain explicit. Normalization to Unknown retains rows.

Complete observed category mappings and full source/member identities/checksums remain in stored metadata. Browser responses omit potentially large raw-value mapping dictionaries and shorten unusually long source labels to 256 characters, with an explicit truncation flag. This prevents successful activation from being reported as a proxy failure because of oversized metadata. Counts and exclusions remain visible.

## Storage and API

Default data root: `backend/.local-data/`. Override with `MOBILITY_DATA_ROOT`. This directory is ignored by Git and contains actual trip data; do not add it to source control.

- `versions/<version_id>/cleaned.csv`: immutable cleaned trip starts.
- `versions/<version_id>/kpis.sqlite`: monthly counts, shares, duration aggregates and version metadata.
- `versions/<version_id>/metadata.json`: quality, source manifest, checksums and normalization dictionary.
- `registry.sqlite`: complete-version registration and the single active pointer per month.
- `quarantine/` and `rejections/`: rejected source bytes under generated names and safe quality evidence, including original source name, checksum and generated quarantine reference.

Persistent writes, checksums and persisted-data reconciliation precede activation. One SQLite transaction changes the active reference. Preparation failure leaves the old reference active; incomplete orphan directories are never auto-activated. Version readers resolve explicit references; multi-period pinning uses one read transaction and remains consistent during replacement. Existing report artifacts are not modified.

| Endpoint | Input | Output |
| --- | --- | --- |
| `POST /ingestions` | Multipart `files`, one or two | Ingestion ID and independent monthly results |
| `POST /ingestions/fetch` | `{"period":{"year":2026,"month":1}}` | Same results from an approved public source |
| `GET /periods` | None | Active period/version references |
| `GET /health` | None | Service health |

Errors retain the safe API envelope and request ID. S3 fetches use fixed HTTPS source URLs, reject redirects, bound response bytes, and try the other approved ZIP suffix only after a 404. Request handling, errors and logs do not expose raw trip rows.

## Final Verification

| Check | Result |
| --- | --- |
| Backend unit/integration | 83 passed; 94.70% statement coverage |
| Frontend unit/integration | 29 passed; 100% lines, 98.4% statements, 89.51% branches, 97.5% functions |
| Live browser tests | 3 passed: health/retry, live proxy health, and upload → accepted correction → rejected correction preserving active version |
| Lint, TypeScript, production webpack build | Passed |
| Shared contracts | Backend snapshot regenerated; frontend generated types match public response projection |
| Python dependency audit | No known vulnerabilities in the final pinned dependencies |
| Real January/February upload | Both accepted; cleaned CSV and SQLite reconcile with checked reference results |

The real-data upload/storage check used isolated temporary storage, not the default application database. [Aggregate evidence](phase-2-real-data.json) records the results without trip rows or local paths. Both months match all reference exclusion counts and denominators, every daily total and the duration sum at source millisecond precision:

| Month | Source rows | Valid trips | Out of month | Missing stations | Duration exclusions |
| --- | ---: | ---: | ---: | ---: | ---: |
| January 2026 | 40,044 | 39,198 | 13 | 825 | 8 |
| February 2026 | 25,809 | 25,387 | 6 | 415 | 1 |

Boundary tests cover exactly 1%, exactly 5%, post-exclusion denominators, duplicate ordering, duration boundaries, Unknown categories, empty data and archive safety. Storage tests cover restart, corruption, failures before activation, interruption after committed activation, historical references, and a concurrent writer during a two-period snapshot. Additional regression tests cover stalled uploads releasing the lock and large category dictionaries remaining on disk while the response stays bounded.

Python, database, security, general, React and TypeScript reviews were performed. Identified functional issues were corrected and regression-tested. Public S3 fallback/network/redirect/size behavior is tested with controlled HTTP responses; the final real-data test used previously verified downloaded archives, not a new live S3 fetch.

## Remaining Scope

Phase 3 adds deterministic dashboard/report generation using these active versions and KPIs. Retention cleanup, hosted authentication/isolation, operational limits, backup/restore and report archives are verified in their affected later phases. No Phase 2 commit or push is implied by local completion.
