"""
WhatsApp Messages API Lambda.

GET /chats  Query params (all optional):
    date    – exact ISO-8601 date (YYYY-MM-DD) to filter the Athena partition
    sender  – partial case-insensitive match on sender name
    search  – partial case-insensitive match on message body
    limit   – max rows to return (default 200, capped at 1000)

Returns JSON array: [{message_id, date, time, sender, message, word_count}]
"""

import json
import os
import time

import boto3

_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
_athena = boto3.client("athena", region_name=_REGION)

DATABASE  = os.environ.get("ATHENA_DATABASE", "")
WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "")

CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}

_MAX_LIMIT     = 1000
_DEFAULT_LIMIT = 200
_POLL_SLEEP    = 0.5   # seconds between status polls
_MAX_POLLS     = 60    # up to 30 seconds total


def _escape_sql_string(value: str) -> str:
    """Escape single quotes for Athena SQL string literals."""
    return value.replace("'", "''")


def _build_query(date=None, sender=None, search=None, limit=_DEFAULT_LIMIT) -> str:
    predicates = []
    if date:
        predicates.append(f"date = '{_escape_sql_string(date)}'")
    if sender:
        predicates.append(f"LOWER(sender) LIKE '%{_escape_sql_string(sender.lower())}%'")
    if search:
        predicates.append(f"LOWER(message) LIKE '%{_escape_sql_string(search.lower())}%'")

    where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    limit = max(1, min(int(limit), _MAX_LIMIT))

    return (
        f"SELECT message_id, date, time, sender, message, word_count "
        f"FROM whatsapp_messages "
        f"{where} "
        f"ORDER BY date DESC, time ASC "
        f"LIMIT {limit}"
    )


def _run_query(sql: str) -> list:
    """Start an Athena query, poll until done, return rows as list of dicts."""
    resp = _athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        WorkGroup=WORKGROUP,
    )
    execution_id = resp["QueryExecutionId"]

    for _ in range(_MAX_POLLS):
        status_resp = _athena.get_query_execution(QueryExecutionId=execution_id)
        state = status_resp["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = status_resp["QueryExecution"]["Status"].get("StateChangeReason", state)
            raise RuntimeError(f"Athena query {state}: {reason}")
        time.sleep(_POLL_SLEEP)
    else:
        raise TimeoutError("Athena query did not complete in time")

    # Paginate through all result pages
    rows = []
    kwargs = {"QueryExecutionId": execution_id}
    first_page = True
    while True:
        result = _athena.get_query_results(**kwargs)
        result_rows = result["ResultSet"]["Rows"]
        col_info = result["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
        column_names = [col["Label"] for col in col_info]
        if first_page:
            result_rows = result_rows[1:]  # skip header row
            first_page = False
        for row in result_rows:
            values = [datum.get("VarCharValue", "") for datum in row["Data"]]
            rows.append(dict(zip(column_names, values)))
        next_token = result.get("NextToken")
        if not next_token:
            break
        kwargs["NextToken"] = next_token

    return rows


def handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    params = event.get("queryStringParameters") or {}
    date   = params.get("date")   or None
    sender = params.get("sender") or None
    search = params.get("search") or None
    try:
        limit = int(params.get("limit", _DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = _DEFAULT_LIMIT

    try:
        sql  = _build_query(date=date, sender=sender, search=search, limit=limit)
        rows = _run_query(sql)
        return {
            "statusCode": 200,
            "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
            "body": json.dumps(rows),
        }
    except Exception as exc:
        return {
            "statusCode": 500,
            "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
            "body": json.dumps({"error": str(exc)}),
        }
