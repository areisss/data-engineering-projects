import re
import urllib.parse
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")

# Matches WhatsApp message lines in US (1/1/24) and international (01/01/2024) formats,
# with or without square-bracket timestamps.
_WHATSAPP_LINE_RE = re.compile(
    r"^\[?\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4},?\s+\d{1,2}:\d{2}"
)


def is_whatsapp_export(content: str) -> bool:
    """Return True if content looks like a WhatsApp chat export (>=2 matching lines)."""
    lines = [line for line in content.splitlines()[:20] if line.strip()]
    matches = sum(1 for line in lines if _WHATSAPP_LINE_RE.match(line))
    return matches >= 2


def bronze_key(filename: str, ts: datetime = None) -> str:
    """Return the Hive-partitioned bronze S3 key for a given filename and timestamp."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    return f"bronze/whatsapp/year={ts.year}/month={ts.month:02d}/{filename}"


def handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        filename = key.split("/")[-1]

        print(f"Processing s3://{bucket}/{key}")

        response = s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8", errors="replace")

        if not is_whatsapp_export(content):
            print(f"Skipped {key}: does not match WhatsApp export format")
            continue

        dest = bronze_key(filename)
        s3.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": key},
            Key=dest,
        )
        print(f"Archived to s3://{bucket}/{dest}")

    return {"statusCode": 200}
