# Checked Cleaning Results — 2026-10-18

These are reference expectations for the exact files in the [dataset manifest](dataset-manifest.md), not production ingestion results. No source files were modified or activated.

## Monthly Cleaning

| Stage | January 2026 | February 2026 |
| --- | --- | --- |
| Parsed rows | 40,044 | 25,809 |
| Invalid timestamp exclusions | 0 | 0 |
| Month threshold denominator | 40,044 | 25,809 |
| Out-of-month exclusions | 13 | 6 |
| Duplicate ride ID exclusions | 0 | 0 |
| Missing-station threshold denominator | 40,031 | 25,803 |
| Missing-station exclusions | 825 | 415 |
| Duration exclusions | 8 | 1 |
| Final valid trips | 39,198 | 25,387 |

Both months pass the unrounded 1% out-of-month and 5% missing-station gates. Exclusions are sequential and non-overlapping. For January: 40,044 − 13 − 825 − 8 = 39,198. For February: 25,809 − 6 − 415 − 1 = 25,387.

Python datetime filtering and independent SQLite date filtering agreed at every cleaning stage and on every retained source-row index. A separate SQL window-function query independently confirmed the investigation candidate. These checks use identical source files; they do not certify source completeness or replace application tests. Timestamps in these files are timezone-naive and were interpreted as America/New_York; neither selected month contains a daylight-saving transition.

Daily starts, station starts, membership counts, and fleet counts reconcile to each final total. Unknown counts are zero in both dimensions for these files. Machine-readable aggregate counts, daily totals, exact duration fractions, and candidate evidence are in [cleaned-expectations.json](cleaned-expectations.json). No raw trip rows are stored there.

## Real Demo Investigation

| Field | Checked result |
| --- | --- |
| Station | River St & Newark St (`HB106`) |
| January starts | 1,584 |
| February starts | 866 |
| Change | -718 trips (-45.33%) |
| Eligibility | Prior ≥ 100, current > 0, decline > 10%, drop > 100 |
| Selection | Largest absolute qualifying drop across all stations; 57 stations qualify |

| Dimension/category | January | February | Delta | Contribution to station change |
| --- | --- | --- | --- | --- |
| member_casual: casual | 222 | 115 | -107 | 14.90% |
| member_casual: member | 1,362 | 751 | -611 | 85.10% |
| rideable_type: classic_bike | 404 | 201 | -203 | 28.27% |
| rideable_type: electric_bike | 1,180 | 665 | -515 | 71.73% |

All four segments meet the prior-count threshold. Members account for 85.10% of the decline, yielding “Primarily driven by [Member]” under the existing template. E-bikes account for 71.73%, yielding “Driven by a mix of factors.” Dimensions overlap and must not be added together. These are decompositions, not causal explanations.

## Verification Limits

These observations prepare reference cases A01–A09 and A16. They do not demonstrate application ingestion, activation, grounding, failure handling, or curator-authored evaluation. Boundary fixtures and review by Abhee, Monisha, and Ashutosh remain pending.
