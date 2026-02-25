"""
Glue PySpark job: WhatsApp bronze → silver.

Reads all .txt files from bronze/whatsapp/, parses each message line into
typed rows with a stable message_id, and writes Snappy-compressed Parquet to
silver/whatsapp/ partitioned by date.  Registers / repairs the Glue catalog
table so Athena can query immediately.

Schedule: daily at 05:00 UTC (Glue trigger) → Crawler at 06:00 UTC.

Silver schema
─────────────
  message_id  STRING   SHA-256(source_file:line_index), first 16 hex chars
  time        STRING   Raw time string from the WhatsApp export
  sender      STRING   Display name of the message author
  message     STRING   Message body text
  word_count  INT      Whitespace-token count of message
  source_file STRING   S3 key of the bronze source file (lineage)
  date        STRING   ISO-8601 YYYY-MM-DD — partition column
"""

import hashlib
import re
import sys
from datetime import datetime
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Pure-Python parsing helpers
# Kept at module level so test_job.py can import them without Spark or Glue.
# ---------------------------------------------------------------------------

# Handles US (M/D/YY) and international (D/M/YYYY) date formats,
# optional square-bracket prefix, and both hyphen and en-dash separators.
_MSG_RE = re.compile(
    r"^\[?(\d{1,2}/\d{1,2}/\d{2,4})\]?,?\s+"
    r"(\d{1,2}:\d{2}(?:\s*[AP]M)?)\s*[-\u2013]\s+"
    r"([^:]+):\s+(.*)",
    re.IGNORECASE,
)

_DATE_FORMATS = ("%m/%d/%y", "%m/%d/%Y", "%d/%m/%y", "%d/%m/%Y")


def parse_date_iso(date_str: str) -> str:
    """Normalise a WhatsApp date string to ISO-8601 YYYY-MM-DD."""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str  # return as-is if no format matches


def make_message_id(source_file: str, line_index: int) -> str:
    """Return a stable 16-char hex ID from SHA-256(source_file:line_index)."""
    payload = f"{source_file}:{line_index}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def parse_file(source_key: str, content: str) -> list:
    """
    Parse a single WhatsApp .txt export into a list of row tuples.

    Each tuple matches SILVER_SCHEMA column order:
      (message_id, time, sender, message, word_count, source_file, date)

    Lines that don't match the WhatsApp timestamp pattern are silently dropped
    (system messages, media-omitted notices, message continuations).
    """
    rows = []
    for i, line in enumerate(content.splitlines()):
        m = _MSG_RE.match(line.strip())
        if not m:
            continue
        date_raw, time_str, sender, message = m.groups()
        message = message.strip()
        rows.append((
            make_message_id(source_key, i),
            time_str.strip(),
            sender.strip(),
            message,
            len(message.split()),
            source_key,
            parse_date_iso(date_raw),
        ))
    return rows


def s3_key_from_uri(uri: str) -> str:
    """Extract the S3 object key from a full S3 URI (any scheme)."""
    return urlparse(uri).path.lstrip("/")


# ---------------------------------------------------------------------------
# Entry point — all Spark / Glue imports live here so the module is importable
# by test_job.py without a Spark/Glue runtime.
# ---------------------------------------------------------------------------

def main():
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext
    from pyspark.sql.types import (
        IntegerType,
        StringType,
        StructField,
        StructType,
    )

    SILVER_SCHEMA = StructType([
        StructField("message_id",  StringType(),  nullable=False),
        StructField("time",        StringType(),  nullable=True),
        StructField("sender",      StringType(),  nullable=True),
        StructField("message",     StringType(),  nullable=True),
        StructField("word_count",  IntegerType(), nullable=True),
        StructField("source_file", StringType(),  nullable=True),
        StructField("date",        StringType(),  nullable=False),  # partition last
    ])

    args = getResolvedOptions(sys.argv, ["JOB_NAME", "BUCKET_NAME", "GLUE_DATABASE"])
    bucket   = args["BUCKET_NAME"]
    database = args["GLUE_DATABASE"]

    sc       = SparkContext()
    glue_ctx = GlueContext(sc)
    spark    = glue_ctx.spark_session
    job      = Job(glue_ctx)
    job.init(args["JOB_NAME"], args)

    # Overwrite only the date-partitions present in this run, leaving others intact.
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

    bronze_prefix = "bronze/whatsapp/"
    silver_path   = f"s3://{bucket}/silver/whatsapp/"

    # ---------------------------------------------------------------------------
    # Use boto3 to list keys explicitly — sc.wholeTextFiles() does not reliably
    # recurse into Hive-partitioned sub-prefixes (year=/month=/) in Glue 4.0.
    # ---------------------------------------------------------------------------
    import boto3 as _boto3
    _s3  = _boto3.client("s3")
    _pag = _s3.get_paginator("list_objects_v2")

    txt_keys = [
        obj["Key"]
        for page in _pag.paginate(Bucket=bucket, Prefix=bronze_prefix)
        for obj in page.get("Contents", [])
        if obj["Key"].endswith(".txt")
    ]

    if not txt_keys:
        print(f"No .txt files under s3://{bucket}/{bronze_prefix} — exiting.")
        job.commit()
        return

    print(f"Found {len(txt_keys)} bronze file(s) to process.")

    # Capture bucket string for closure serialisation (avoids serialising `args`).
    _bucket = bucket

    def _read_and_parse(key):
        """Worker closure: fetch one S3 object and parse it."""
        import boto3 as _b3
        _s3w = _b3.client("s3")
        resp    = _s3w.get_object(Bucket=_bucket, Key=key)
        content = resp["Body"].read().decode("utf-8", errors="replace")
        return parse_file(key, content)

    rows_rdd = sc.parallelize(txt_keys, numSlices=len(txt_keys)).flatMap(_read_and_parse)

    if rows_rdd.isEmpty():
        print("No parseable WhatsApp messages found in bronze files — exiting.")
        job.commit()
        return

    df    = spark.createDataFrame(rows_rdd, schema=SILVER_SCHEMA)
    total = df.count()
    print(f"Parsed {total} messages — writing to {silver_path}")

    (
        df.write
        .mode("overwrite")
        .partitionBy("date")
        .option("compression", "snappy")
        .parquet(silver_path)
    )

    # Register the table in the Glue catalog.  DROP + CREATE ensures the schema
    # stays in sync with the code across deployments.  Dropping an EXTERNAL TABLE
    # never deletes S3 data.
    spark.sql(f"DROP TABLE IF EXISTS `{database}`.`whatsapp_messages`")
    spark.sql(f"""
        CREATE EXTERNAL TABLE `{database}`.`whatsapp_messages` (
            message_id  STRING  COMMENT 'SHA-256(source_file:line_index), 16 hex chars',
            time        STRING  COMMENT 'Raw time string from WhatsApp export',
            sender      STRING  COMMENT 'Message sender display name',
            message     STRING  COMMENT 'Message body text',
            word_count  INT     COMMENT 'Whitespace-delimited token count',
            source_file STRING  COMMENT 'S3 key of the bronze source file'
        )
        PARTITIONED BY (date STRING COMMENT 'ISO-8601 message date, partition key')
        STORED AS PARQUET
        LOCATION '{silver_path}'
        TBLPROPERTIES ('parquet.compress' = 'SNAPPY')
    """)
    spark.sql(f"MSCK REPAIR TABLE `{database}`.`whatsapp_messages`")

    print(f"Catalog table `{database}`.`whatsapp_messages` updated — {total} rows written.")
    job.commit()


if __name__ == "__main__":
    main()
