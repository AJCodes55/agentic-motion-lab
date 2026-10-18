# Dataset Manifest — Verified 2026-10-18

Source: public Citi Bike S3 bucket. Object names were verified through bucket prefix listings, then downloaded to temporary storage. ZIP CRC checks passed. Each CSV has the exact 13 SRS columns. Counts below exclude the header and precede all cleaning; they are not final valid-trip totals or proof of complete calendar coverage.

| Period | Official source | Archive bytes | CSV member | Parsed rows |
| --- | --- | --- | --- | --- |
| 2026-01, prior | [January ZIP](https://s3.amazonaws.com/tripdata/JC-202601-citibike-tripdata.zip) | 1,441,549 | `JC-202601-citibike-tripdata.csv` | 40,044 |
| 2026-02, current | [February ZIP](https://s3.amazonaws.com/tripdata/JC-202602-citibike-tripdata.csv.zip) | 958,731 | `JC-202602-citibike-tripdata.csv` | 25,809 |

| Artifact | SHA-256 |
| --- | --- |
| January ZIP | `0178780d0dfdfe2f9170681a8e1964bd1120414b4af61f3adc75c9580947c9bb` |
| January CSV, 8,672,671 bytes | `4026187c1db744f1cf102b93676d604f6f8581df1cc91f7383f20e333d81c838` |
| February ZIP | `e35fd1f94ac9f5fd2a1ab761a3b46828da590f081cd3f31ce079a0a1351252ee` |
| February CSV, 5,606,126 bytes | `10c26397d4bd3801af1a120bb8ebcd59eff5dd498b26e14b526a0f51ac8770bd` |

Additional archive members, ignored under the approved metadata rule:

- January: `__MACOSX/._JC-202601-citibike-tripdata.csv`, 598 bytes, SHA-256 `90f1bf7c64712b3464b29ce9f6c9dab50e2d8ba15c21cbe432ee3fd8168bfc6b`.
- February: `__MACOSX/._JC-202602-citibike-tripdata.csv`, 498 bytes, SHA-256 `0dd85b2905bb98b1c335c47dabf58e478866508c0111d7a6c09fbc78166efc13`.

Each selected archive contains exactly one data CSV, so there is no within-archive concatenation tie. Preserve CSV row order for these inspections. Approved ZIP formats are `JC-YYYYMM-citibike-tripdata.zip` and `JC-YYYYMM-citibike-tripdata.csv.zip`; data CSVs use `JC-YYYYMM-citibike-tripdata.csv`. Process uploaded files and archive data members alphabetically by filename, preserving CSV row order. Group by filename-defined month and validate each month separately. Multipart filename variants beyond these formats remain unapproved.

Raw category counts:

| Raw value | Approved label | January | February |
| --- | --- | --- | --- |
| `member` | Member | 34,566 | 22,261 |
| `casual` | Casual | 5,478 | 3,548 |
| `classic_bike` | Classic | 12,547 | 8,235 |
| `electric_bike` | E-bike | 27,497 | 17,574 |
| Other values, in either dimension | Unknown | 0 | 0 |

Verification used Python standard-library `csv.DictReader`, with a separate `csv.reader` pass to confirm logical record counts. Both passes agreed for both files. Each category dimension sums to its source count. These checks share a CSV parser and do not replace independently checked cleaned expectations. No raw rows were sent to an LLM.


Cleaning-stage reference totals and the independently confirmed demo candidate are now recorded in [checked cleaning results](cleaned-expectations.md). Parsed source counts above remain unchanged.
