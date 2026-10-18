# Boundary Cases for Curator Review

Status: assistant-prepared review draft, 2026-10-18. These are concrete synthetic fixture specifications, not executed application tests and not contributions authored or approved by the named curators. Real-data expectations remain separate in [checked results](cleaned-expectations.md).

## How to Review

1. Review the cases for your assigned domain below.
2. Record a correction or approval and add at least one challenging case of your own.
3. Record your name, fixture/version, expected route, figures, tool sequence, and terminal state. Observed results and execution evidence remain pending until the application exists.

Ashutosh reviews ingestion and agent behavior. Abhee and Monisha review analytics together; their individual case split remains pending. Each case ID below is a stable synthetic dataset/scenario reference. Every case currently has author = assistant, curator review = pending, execution = not run.

## Ingestion — Ashutosh

Unless overridden, use a canonical January 2026 CSV with all 13 SRS columns, unique nonempty ride IDs, valid start/end station IDs, local January start/end timestamps, 120-second durations, `member`, and `classic_bike`. Generated records stay synthetic. Alter only the stated fields. Threshold rows are distinct unless a case explicitly introduces duplicates. All exclusions follow the SRS sequence.

| ID / acceptance | Input or mutation | Expected result |
| --- | --- | --- |
| I01 / A02 | 100 timestamp-valid rows; 1 starts in December. | Month denominator 100; 1% accepted; exclude 1; final 99. |
| I02 / A02 | 100 timestamp-valid rows; 2 start in December. | 2% exceeds 1%; reject month; preserve prior active version. |
| I03 / A02 | 101 rows: 1 invalid timestamp, then 1 out-of-month among 100 valid. | Exclude invalid first; month denominator 100, not 101; accept at 1%; final 99. |
| I04 / A02 | 3 rows: invalid start, null end, invalid end respectively. | Exclude all 3; zero month denominator; reject. |
| I05 / A03 | 101 same-month rows; one repeated ride ID is the final row; after deduplication exactly 5 distinct rows lack station IDs. | Deduplicate first: denominator 100; 5/100 = 5%; reject, even though 5/101 is below 5%. |
| I06 / A03 | 101 unique same-month rows; 5 lack station IDs. | 5/101 is below 5%; exclude 5; final 96. Do not round to decide. |
| I07 / A03 | Two canonical January inputs: raw CSV and ZIP containing a CSV. Pass them in reverse filename order. The alphabetically first uploaded filename has ride ID R1 as Member; the other repeats R1 as Casual. All other rows valid. | Sort uploaded filenames first; retain first R1 and its Member value; one duplicate excluded. Preserve row order. Same-month grouping precedes cleaning. |
| I08 / A04 | Four rows with durations 59, 60, 86,400, and 86,401 seconds, all starting January 10. | Retain 60 and 86,400 only; 2 duration exclusions; final 2. |
| I09 / A04 | Two valid rows: one Member/Classic; one unexpected membership and fleet strings. | Final 2; each dimension has 1 known and 1 Unknown; shares 50% each; no category exclusion. |
| I10 / A04 | One valid-timestamp, same-month row with 59-second duration. | Final zero after duration exclusion; reject; no baseline if no active dataset. |
| I11 / A03 | 100 unique valid rows; one has blank start ID, one has whitespace end ID, one has NaN start ID, one lacks both IDs. | Four affected rows, not five; 4% accepted; final 96. |
| I12 / A01,A18 | One January archive; then a separate scenario with January and February archives together; then zero files; then three files. | One/two accepted for validation; group and validate months separately; zero/three rejected. ZIP members do not count as uploaded files. Cross-month activation atomicity is not specified by this case. |
| I13 / A01,A17 | Valid archive plus `__MACOSX/._…` metadata; separate hostile archive with `../escape.csv`; separate CSV missing `ride_id`. | Ignore metadata; reject traversal without writing outside extraction root; reject missing column with `ERR_SCHEMA_MISMATCH`; no activation on either rejection. |
| I14 / A05 | Run I03, then I06 separately. | I03 reconciles 101 − 1 − 1 = 99; I06 reconciles 101 − 5 = 96; per-file, lake, SQLite, daily, station and category totals agree after implementation. |

I07 deliberately uses only approved filenames. Multi-CSV member naming beyond the approved grammar remains unsupported until explicitly approved; do not invent multipart filenames to implement this fixture.

## Analytics — Abhee and Monisha

Use synthetic aggregate fixtures identified by case ID; periods are January (prior) and February (current) unless stated otherwise. Station IDs are literal strings. Values are exact counts. These are tool-level fixtures, not uploaded monthly source files.

| ID / acceptance | Inputs | Expected result |
| --- | --- | --- |
| N01 / A07 | Station S: prior 99, current 50. | Delta −49; percentage null/ineligible, not zero; still eligible for absolute decrease ranking. |
| N02 / A07 | Station S: prior 100, current 50. | Delta −50; percentage −50%; Significant Change, downward; no mandatory trigger because drop ≤100. |
| N03 / A07,A08 | New N: 0→150; removed R: 150→0. | New/removed labels; percentages null; include in absolute rankings; neither triggers investigation. |
| N04 / A07 | Separate stations: 1000→951, 1000→950, 1000→900, 1000→899. | Changes −4.9% Flat; −5% Moderate Change; −10% Moderate Change; −10.1% Significant Change. Thresholds use unrounded values. |
| N05 / A08 | Separate stations: 2000→1800; 500→400; 1000→899. | Exactly 10% fails trigger; exactly 100-trip drop fails trigger; 101-trip and 10.1% decline qualifies. |
| N06 / A08 | Removed stations R1–R5: 1000/900/800/700/600→0 respectively; station S: 500→399. | Display top five decreases R1–R5; mandatory candidate S despite being outside displayed five. |
| N07 / A08 | Stations A and B both 1000→800. | Equal 200-trip drop: A precedes B in ranking and is mandatory candidate. |
| N08 / A09 | Same station: Member 100→20; Casual 100→80; Unknown 0→0. Total 200→100. Fleet independently Classic 100→50, E-bike 100→50. | Member 80%, Casual 20%: “Primarily driven by [Member].” Fleet leaders tie at 50%; show both, never add membership and fleet contributions. Exact tied narrative remains pending D02. |
| N09 / A09 | Membership: Member 100→0, Casual 100→100. Total 200→100. | Member contribution exactly 100%: “Driven entirely by [Member].” |
| N10 / A09 | Membership: Member 200→80, Casual 100→120. Total 300→200. | Member 120%, Casual −20%; “More than accounted for by [Member].” Contributions may exceed 100% or be negative. |
| N11 / A09 | Membership: Member 100→40, Casual 100→60. Total 200→100. | Contributions 60% and 40%; “Driven by a mix of factors.” |
| N12 / A09 | Membership: Member 100→80, Unknown 200→120. Total 300→200. | Unknown 80% is eligible leader; exactly “Driven primarily by unclassified data.” |
| N13 / A09 | Membership: Member 100→50, Unknown 100→50. Total 200→100. | Both tie at 50%; display Member and Unknown, explicitly label unclassified contribution; do not silently choose Unknown alone. Exact tie text pending D02. |
| N14 / A09 | Membership: Member 100→110, Casual 100→90. Total 200→200. | Zero total delta; all contributions null; suppress contribution sentences. |
| N15 / A09 | Membership: Member 99→0, Casual 101→100. Total 200→100. | Member contribution null because own prior sample is 99; Casual contribution 1%; no claim using ineligible 99%. |
| N16 / A07 | Two valid starts at station A; one is Member/Classic lasting 60 seconds, one Casual/E-bike lasting 180 seconds. Add arrivals at A from other stations in a separate station aggregation fixture. | A starts remain 2; average 2 minutes; each mix 50/50; arrivals do not inflate starts. |
| N17 / A07,A11,A18 | January has day 31; February ends day 28; fixture share is exactly 1/3 × 100%. | Align day numbers; February days 29–31 are gaps; render share 33.33%, retain exact unrounded evidence. |
| N18 / A07 | Compare January 2026 to December 2025; separate request compares February to December. | First is adjacent across year boundary; second is unsupported non-adjacent comparison. |

## Agent Behavior — Ashutosh

Unless overridden, a deterministic baseline already exists; pinned versions are `synthetic_jan_v1` and `synthetic_feb_v1`. These labels are fixture identities, not deployed versions. Use candidate S with prior 500 and current 399. Initial successful `station_movers` evidence identifies S; successful variance evidence must contain both dimensions. Case mutations below are separate runs.

| ID / acceptance | Request or mutation | Expected route, sequence, and terminal result |
| --- | --- | --- |
| G01 / A10 | “Generate February 2026 report”; only February is available. | Standard standalone baseline, note missing MoM; lookup before plan; no attempted missing-period comparison. |
| G02 / A10 | “Compare station S in February 2026 with January”; only February available. | Refusal `ERR_UNSUPPORTED_INTENT`, explain missing prior and offer single-month alternative; no upload request mid-run. |
| G03 / A10 | Separate requests: forecast March; explain decline due to weather; compare December to February; show three-month trend; calculate median duration. | Refuse each unsupported request with supported alternative; no unsupported analytical tool dispatched. |
| G04 / A12 | “Generate February 2026 report”; candidate S exists. | Baseline outside loop; available-period lookup before validated plan; movers before selected variance(S, February, January); successful both-dimension result before validated claims; completed grounded report. |
| G05 / A12,A14 | After candidate S, separately return variance for station X, wrong current month, wrong prior month, failed status, or missing fleet dimension. | Each fails follow-up gate; consumes its one retry, replans within remaining budgets; never accepts failed/incomplete evidence. |
| G06 / A13 | Valid current-volume evidence: run R1, call E1, S, February, 399 trips, February v1. Change one identity field at a time: month, station, metric, comparison period, category, dimension, unit, value, version, or run. Also try invented call ID and failed-call evidence. | Each incompatible claim rejected with `ERR_UNGROUNDED_CLAIM`; one gate retry; no failed draft displayed. Equal numbers elsewhere do not rescue attribution. |
| G07 / A13 | Correct successful current-volume claim against E1 from G06; separately reference successful baseline evidence from this run. | Exact composite identities pass; baseline reuse requires no redundant selected tool call; Python formats verified text. |
| G08 / A14 | Already 10 selected tool invocations; attempt an eleventh. Separately already 6 LLM calls; attempt seventh. | Block before dispatch; `ERR_BUDGET_EXCEEDED`; baseline only with exact budget warning below. Failed selected calls and retries count. |
| G09 / A14 | Same named result-validation gate fails; retry fails; later code revisits gate. | No second retry allocation; baseline only with exact narrative warning below. No LLM-selected narrative retained. |
| G10 / A10 | Two station IDs share name “Central”; request station Central, February 2026. | Ask user to select station; do not guess. New request without station cannot borrow previous analytical chat context. |
| G11 / A06,A13 | Run pins February v1, corrected upload activates v2 mid-run. | Existing run consistently uses v1; future run uses v2; old archive HTML/assets and source metadata are not rewritten. |
| G12 / A06 | Interrupt replacement before activation; separately interrupt after activation commit. | Before commit old version remains active; after commit new version is complete/queryable; no mixed lake/KPI pointers; orphan version cannot activate. |

Exact fallback messages:

- Budget: “Pass with limitations: Reasoning budget exhausted. Displaying standard baseline metrics only.”
- Exhausted validation retry: “Pass with limitations: Narrative validation failed. Displaying standard baseline metrics only.”

## Review Record

| Domain | Requested reviewers | Review status | Human-authored additional case |
| --- | --- | --- | --- |
| Ingestion | Ashutosh | All I01–I14 approved by the user on 2026-10-18 | Pending |
| Analytics | Abhee and Monisha; case split pending | All N01–N18 approved by the user on 2026-10-18 | One from each curator pending |
| Agent behavior | Ashutosh | All G01–G12 approved by the user on 2026-10-18 | Pending |

Curators should append their review notes and cases here or link a reviewed fixture artifact. Do not change review status merely because an assistant checks arithmetic. Production authentication, resource-limit values, retention semantics, and exact tie text remain deferred decisions; this pack does not supply them.

### Approval Record

On 2026-10-18, the user replied “lgtm , approved” to the request to review I01–I03. Approval is recorded for those three case specifications. The approver's identity was not explicitly supplied, so this is not attributed to Ashutosh by name. This approval does not establish test execution, approval of the remaining cases, or a human-authored additional case.

Subsequently, on 2026-10-18, the user explicitly confirmed reviewing everything and approved the complete 44-case pack. This supersedes the earlier partial approval. All case specifications are user-approved; application execution remains not run. This approval is not attributed to each named curator individually and does not substitute for each curator contributing a challenging case during evaluation preparation.
