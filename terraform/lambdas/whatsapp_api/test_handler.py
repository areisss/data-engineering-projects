"""Tests for whatsapp_api/handler.py"""

import json
from unittest.mock import MagicMock, patch

import pytest

import handler


# ---------------------------------------------------------------------------
# _build_query
# ---------------------------------------------------------------------------

class TestBuildQuery:
    def test_no_params_has_no_where(self):
        sql = handler._build_query()
        assert "FROM whatsapp_messages" in sql
        assert "WHERE" not in sql
        assert "LIMIT 200" in sql

    def test_default_sort(self):
        sql = handler._build_query()
        assert "ORDER BY date DESC, time ASC" in sql

    def test_date_filter(self):
        sql = handler._build_query(date="2023-07-04")
        assert "date = '2023-07-04'" in sql
        assert "WHERE" in sql

    def test_sender_filter_lowercased(self):
        sql = handler._build_query(sender="Alice")
        assert "LOWER(sender) LIKE '%alice%'" in sql

    def test_search_filter_lowercased(self):
        sql = handler._build_query(search="Hello World")
        assert "LOWER(message) LIKE '%hello world%'" in sql

    def test_all_filters_joined_with_and(self):
        sql = handler._build_query(date="2023-01-01", sender="Bob", search="hi")
        assert "date = '2023-01-01'" in sql
        assert "LOWER(sender) LIKE '%bob%'" in sql
        assert "LOWER(message) LIKE '%hi%'" in sql
        assert "AND" in sql

    def test_custom_limit(self):
        sql = handler._build_query(limit=50)
        assert "LIMIT 50" in sql

    def test_limit_capped_at_max(self):
        sql = handler._build_query(limit=9999)
        assert "LIMIT 1000" in sql

    def test_limit_minimum_is_one(self):
        sql = handler._build_query(limit=0)
        assert "LIMIT 1" in sql

    def test_sql_injection_single_quote_escaped(self):
        # The single quote is doubled so the injected text remains inside the string literal.
        sql = handler._build_query(date="2023-07-04'; DROP TABLE whatsapp_messages; --")
        # Escaped quote is present, confirming the value is wrapped in a string literal
        assert "''" in sql
        # The whole injected value is enclosed between the outer quotes
        assert "date = '2023-07-04''; DROP TABLE whatsapp_messages; --'" in sql


# ---------------------------------------------------------------------------
# _run_query
# ---------------------------------------------------------------------------

def _make_athena_mock(state="SUCCEEDED", rows=None):
    """Return a mock Athena client that responds with given state and rows."""
    mock = MagicMock()
    mock.start_query_execution.return_value = {"QueryExecutionId": "qid-123"}
    mock.get_query_execution.return_value = {
        "QueryExecution": {"Status": {"State": state}}
    }
    col_info = [
        {"Label": "message_id"},
        {"Label": "date"},
        {"Label": "time"},
        {"Label": "sender"},
        {"Label": "message"},
        {"Label": "word_count"},
    ]
    header = {"Data": [{"VarCharValue": c["Label"]} for c in col_info]}
    data_rows = [
        {"Data": [{"VarCharValue": str(v)} for v in row]}
        for row in (rows or [])
    ]
    mock.get_query_results.return_value = {
        "ResultSet": {
            "Rows": [header] + data_rows,
            "ResultSetMetadata": {"ColumnInfo": col_info},
        }
    }
    return mock


class TestRunQuery:
    def test_returns_rows_as_dicts(self):
        mock_athena = _make_athena_mock(
            rows=[["id1", "2023-07-04", "10:00", "Alice", "Hello", "1"]]
        )
        with patch.object(handler, "_athena", mock_athena):
            rows = handler._run_query("SELECT 1")
        assert len(rows) == 1
        assert rows[0]["sender"] == "Alice"
        assert rows[0]["message"] == "Hello"
        assert rows[0]["date"] == "2023-07-04"

    def test_empty_result_set(self):
        mock_athena = _make_athena_mock(rows=[])
        with patch.object(handler, "_athena", mock_athena):
            rows = handler._run_query("SELECT 1")
        assert rows == []

    def test_failed_query_raises_runtime_error(self):
        mock_athena = _make_athena_mock(state="FAILED")
        mock_athena.get_query_execution.return_value = {
            "QueryExecution": {
                "Status": {"State": "FAILED", "StateChangeReason": "Table not found"}
            }
        }
        with patch.object(handler, "_athena", mock_athena):
            with pytest.raises(RuntimeError, match="FAILED"):
                handler._run_query("SELECT 1")

    def test_cancelled_query_raises_runtime_error(self):
        mock_athena = _make_athena_mock(state="CANCELLED")
        mock_athena.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "CANCELLED"}}
        }
        with patch.object(handler, "_athena", mock_athena):
            with pytest.raises(RuntimeError, match="CANCELLED"):
                handler._run_query("SELECT 1")

    def test_uses_start_query_execution(self):
        mock_athena = _make_athena_mock()
        with patch.object(handler, "_athena", mock_athena):
            handler._run_query("SELECT 42")
        mock_athena.start_query_execution.assert_called_once()
        call_kwargs = mock_athena.start_query_execution.call_args.kwargs
        assert call_kwargs["QueryString"] == "SELECT 42"


# ---------------------------------------------------------------------------
# handler (integration)
# ---------------------------------------------------------------------------

class TestHandler:
    def _make_event(self, params=None):
        return {
            "httpMethod": "GET",
            "queryStringParameters": params or {},
        }

    def test_options_returns_200(self):
        resp = handler.handler({"httpMethod": "OPTIONS"}, None)
        assert resp["statusCode"] == 200

    def test_get_returns_messages_list(self):
        mock_rows = [
            {"message_id": "abc", "date": "2023-07-04", "time": "10:00",
             "sender": "Alice", "message": "Hi", "word_count": "1"}
        ]
        with patch.object(handler, "_run_query", return_value=mock_rows):
            resp = handler.handler(self._make_event(), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body) == 1
        assert body[0]["sender"] == "Alice"

    def test_get_passes_filters_to_build_query(self):
        with patch.object(handler, "_run_query", return_value=[]):
            with patch.object(handler, "_build_query", return_value="SELECT 1") as mock_bq:
                handler.handler(
                    self._make_event({"date": "2023-07-04", "sender": "Bob", "search": "hi"}),
                    None,
                )
        mock_bq.assert_called_once_with(date="2023-07-04", sender="Bob", search="hi", limit=200)

    def test_invalid_limit_falls_back_to_default(self):
        with patch.object(handler, "_run_query", return_value=[]):
            with patch.object(handler, "_build_query", return_value="SELECT 1") as mock_bq:
                handler.handler(self._make_event({"limit": "notanumber"}), None)
        mock_bq.assert_called_once_with(date=None, sender=None, search=None, limit=200)

    def test_athena_error_returns_500(self):
        with patch.object(handler, "_run_query", side_effect=RuntimeError("Athena error")):
            resp = handler.handler(self._make_event(), None)
        assert resp["statusCode"] == 500
        body = json.loads(resp["body"])
        assert "error" in body
        assert "Athena error" in body["error"]

    def test_cors_headers_present_on_success(self):
        with patch.object(handler, "_run_query", return_value=[]):
            resp = handler.handler(self._make_event(), None)
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_cors_headers_present_on_error(self):
        with patch.object(handler, "_run_query", side_effect=RuntimeError("boom")):
            resp = handler.handler(self._make_event(), None)
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_null_query_params_handled(self):
        event = {"httpMethod": "GET", "queryStringParameters": None}
        with patch.object(handler, "_run_query", return_value=[]):
            resp = handler.handler(event, None)
        assert resp["statusCode"] == 200

    def test_empty_params_treated_as_none(self):
        with patch.object(handler, "_run_query", return_value=[]):
            with patch.object(handler, "_build_query", return_value="SELECT 1") as mock_bq:
                handler.handler(self._make_event({"date": "", "sender": ""}), None)
        mock_bq.assert_called_once_with(date=None, sender=None, search=None, limit=200)
