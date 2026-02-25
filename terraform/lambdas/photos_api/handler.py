import json
import os
from decimal import Decimal

import boto3

_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
s3 = boto3.client("s3", region_name=_REGION)
dynamodb = boto3.resource("dynamodb", region_name=_REGION)

BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "")

THUMBNAIL_URL_TTL = 3_600    # 1 hour
ORIGINAL_URL_TTL = 86_400    # 24 hours

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}

_VALID_SORT_FIELDS = {"taken_at", "uploaded_at"}


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def scan_all(table):
    """Scan a DynamoDB table, handling pagination automatically."""
    items = []
    kwargs = {}
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def apply_filters_and_sort(items, sort_by="uploaded_at", tag=None):
    """Filter by tag and sort descending by sort_by field, nulls last.

    sort_by: "uploaded_at" (default) or "taken_at"
    tag:     case-insensitive match against each item's tags list; None = no filter
    """
    if tag:
        tag_lower = tag.lower()
        items = [
            item for item in items
            if tag_lower in [t.lower() for t in item.get("tags", [])]
        ]

    field = sort_by if sort_by in _VALID_SORT_FIELDS else "uploaded_at"
    # Items missing the sort field get "" which sorts before any ISO timestamp,
    # so with reverse=True they naturally fall to the end of the list.
    items.sort(key=lambda x: x.get(field) or "", reverse=True)
    return items


def build_photo_response(item):
    """Augment a DynamoDB item with pre-signed S3 URLs."""
    thumbnail_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": item["thumbnail_key"]},
        ExpiresIn=THUMBNAIL_URL_TTL,
    )
    original_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": item["original_key"]},
        ExpiresIn=ORIGINAL_URL_TTL,
    )
    return {**item, "thumbnail_url": thumbnail_url, "original_url": original_url}


def handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    params  = event.get("queryStringParameters") or {}
    sort_by = params.get("sort_by", "uploaded_at")
    tag     = params.get("tag") or None

    table = dynamodb.Table(TABLE_NAME)
    items = scan_all(table)
    items = apply_filters_and_sort(items, sort_by=sort_by, tag=tag)

    photos = [build_photo_response(item) for item in items]

    return {
        "statusCode": 200,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(photos, default=_decimal_default),
    }
