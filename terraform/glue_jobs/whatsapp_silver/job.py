"""
Glue Python Shell job: WhatsApp bronze → silver.

Reads all .txt files from bronze/whatsapp/, parses them into structured rows,
and writes Parquet to silver/whatsapp/ partitioned by date. Also registers /
updates the Glue catalog table so Athena can query it immediately.

Scheduled daily at 05:00 UTC (before the Glue Crawler at 06:00 UTC).
"""
import re
import sys
from datetime import datetime

import boto3
import pandas as pd

# ---------------------------------------------------------------------------
# Job parameters (injected by Glue; fall back for local/test runs)
# ---------------------------------------------------------------------------
try:
    from awsglue.utils import getResolvedOptions

    _args = getResolvedOptions(sys.argv, ["BUCKET_NAME", "GLUE_DATABASE"])
    BUCKET_NAME = _args["BUCKET_NAME"]
    GLUE_DATABASE = _args["GLUE_DATABASE"]
except (ImportError, SystemExit):
    BUCKET_NAME = ""
    GLUE_DATABASE = ""

# ---------------------------------------------------------------------------
# Parsing helpers (pure functions — imported directly by test_job.py)
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
    """Convert a WhatsApp date string to ISO-8601 (YYYY-MM-DD)."""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str  # return as-is if no format matches


def parse_chat(content: str) -> pd.DataFrame:
    """Parse the full text of a WhatsApp export into a DataFrame.

    Columns: date (ISO), time, sender, message
    """
    rows = []
    for line in content.splitlines():
        m = _MSG_RE.match(line.strip())
        if m:
            date_raw, time_str, sender, message = m.groups()
            rows.append(
                {
                    "date": parse_date_iso(date_raw),
                    "time": time_str.strip(),
                    "sender": sender.strip(),
                    "message": message.strip(),
                }
            )
    return pd.DataFrame(rows, columns=["date", "time", "sender", "message"])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import awswrangler as wr  # imported here so tests don't require it

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")

    dfs = []
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix="bronze/whatsapp/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".txt"):
                continue
            response = s3.get_object(Bucket=BUCKET_NAME, Key=key)
            content = response["Body"].read().decode("utf-8", errors="replace")
            df = parse_chat(content)
            if not df.empty:
                df["source_file"] = key
                dfs.append(df)

    if not dfs:
        print("No bronze files to process — exiting.")
        return

    combined = pd.concat(dfs, ignore_index=True)
    print(f"Writing {len(combined)} messages from {len(dfs)} files to silver layer")

    wr.s3.to_parquet(
        df=combined,
        path=f"s3://{BUCKET_NAME}/silver/whatsapp/",
        partition_cols=["date"],
        dataset=True,
        database=GLUE_DATABASE,
        table="whatsapp_messages",
        mode="overwrite_partitions",
    )
    print("Silver layer updated successfully")


if __name__ == "__main__":
    main()
