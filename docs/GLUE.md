# Glue Job: whatsapp_silver

**Source**: `terraform/glue_jobs/whatsapp_silver/job.py`
**Type**: Python Shell (Glue 3.0, Python 3.9)
**Capacity**: 0.0625 DPU (minimum)
**Timeout**: 60 minutes
**Schedule**: Daily at **05:00 UTC** (one hour before the Glue Crawler at 06:00 UTC)

---

## Purpose

Reads all validated WhatsApp chat exports from the bronze layer, parses each message line into structured columns, and writes the result as Parquet to the silver layer partitioned by date. Also registers or updates the Glue catalog table so Athena can query it immediately without waiting for the Crawler.

---

## Input

| Detail | Value |
|---|---|
| S3 prefix | `s3://<bucket>/bronze/whatsapp/` |
| File format | `.txt` (UTF-8, errors replaced) |
| Partition layout | `year=YYYY/month=MM/<filename>.txt` (Hive-style, written by `whatsapp_bronze` Lambda) |

The job lists all objects under `bronze/whatsapp/` using a paginated `ListObjectsV2` call and reads every `.txt` file regardless of partition. Non-`.txt` keys are skipped.

---

## Parsing

Each line is matched against a regex that handles:
- US date format: `M/D/YY` or `M/D/YYYY`
- International date format: `D/M/YY` or `D/M/YYYY`
- Optional square-bracket prefix: `[1/1/24, 10:00]` or `1/1/24, 10:00`
- Both hyphen (`-`) and en-dash (`–`) as the sender separator
- Optional AM/PM in the time component

Lines that do not match (system messages, media omitted notices, line continuations) are silently dropped.

Each matching line produces one row:

| Column | Type | Example |
|---|---|---|
| `date` | string (ISO-8601) | `2024-03-15` |
| `time` | string | `10:32 AM` |
| `sender` | string | `Alice` |
| `message` | string | `Hello there!` |

Date strings are normalised to `YYYY-MM-DD`. Four formats are attempted in order: `%m/%d/%y`, `%m/%d/%Y`, `%d/%m/%y`, `%d/%m/%Y`. If none match, the raw date string is kept as-is.

A `source_file` column is appended to each row recording the S3 key the line came from.

---

## Output

| Detail | Value |
|---|---|
| S3 path | `s3://<bucket>/silver/whatsapp/` |
| File format | Parquet |
| Partition column | `date` (daily) |
| Write mode | `overwrite_partitions` — re-running on the same day overwrites only affected date partitions; older partitions are untouched |
| Catalog registration | `awswrangler` writes directly to the Glue catalog database (`<project>_<env>`) as table `whatsapp_messages` |

If there are no `.txt` files in the bronze layer the job logs "No bronze files to process" and exits cleanly without writing anything.

---

## Job parameters

Injected by Glue at runtime via `getResolvedOptions`:

| Parameter | Terraform source | Description |
|---|---|---|
| `--BUCKET_NAME` | `var.bucket_id` | S3 bucket name for both input and output |
| `--GLUE_DATABASE` | `aws_glue_catalog_database.main.name` | Target Glue catalog database |
| `--additional-python-modules` | hardcoded `awswrangler` | Installed by Glue before the job starts |

The job falls back to empty strings for `BUCKET_NAME` and `GLUE_DATABASE` when the Glue SDK is not present (i.e. in local test runs).

---

## Glue Crawler

A separate Glue Crawler (`whatsapp_silver`) runs at **06:00 UTC** — one hour after the job. It targets `s3://<bucket>/silver/whatsapp/` and refreshes the Glue catalog with any new partitions.

The job already registers partitions via `awswrangler` (`mode=overwrite_partitions` updates the catalog in-process), so the Crawler is a safety net for edge cases where the catalog and S3 state drift, not a primary path.

---

## Error handling

The job has no explicit `try/except`. Any unhandled exception (S3 read error, parse failure on a corrupt file, Parquet write error) fails the entire job run. Glue does not automatically retry scheduled jobs on failure — a failed run must be re-triggered manually from the AWS console or CLI:

```bash
aws glue start-job-run \
  --job-name data-engineering-whatsapp-silver-dev \
  --profile personal --region us-east-1
```

Re-running is safe: `overwrite_partitions` mode means re-processing already-written date partitions replaces them cleanly.

The job does **not** move or delete bronze files after processing — bronze is append-only and every run re-reads all files. This means the silver layer is always a full recompute from bronze.

---

## Running locally

```bash
cd terraform/glue_jobs/whatsapp_silver
pip install pandas pyarrow awswrangler
python -m pytest test_job.py
```

The test file imports `parse_date_iso` and `parse_chat` directly (the pure-function helpers) without requiring the Glue SDK or live AWS. The `main()` function (which calls `awswrangler`) is not exercised in tests.
