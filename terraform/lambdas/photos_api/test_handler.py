import json
import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("BUCKET_NAME", "test-bucket")
os.environ.setdefault("TABLE_NAME", "test-table")

import handler as h  # noqa: E402


def make_item(photo_id, uploaded_at, width=100, height=100,
              taken_at=None, tags=None):
    item = {
        "photo_id": photo_id,
        "uploaded_at": uploaded_at,
        "thumbnail_key": f"photos/thumbnails/{photo_id}.jpg",
        "original_key": f"photos/originals/{photo_id}.jpg",
        "filename": f"{photo_id}.jpg",
        "width": Decimal(width),
        "height": Decimal(height),
        "size_bytes": Decimal(1024),
        "content_type": "image/jpeg",
    }
    if taken_at is not None:
        item["taken_at"] = taken_at
    if tags is not None:
        item["tags"] = tags
    return item


@pytest.fixture(autouse=True)
def mock_aws(monkeypatch):
    """Replace module-level boto3 clients with mocks before every test."""
    mock_s3 = MagicMock()
    mock_dynamo = MagicMock()
    monkeypatch.setattr(h, "s3", mock_s3)
    monkeypatch.setattr(h, "dynamodb", mock_dynamo)
    mock_s3.generate_presigned_url.side_effect = (
        lambda op, Params, ExpiresIn: f"https://s3.example.com/{Params['Key']}?expires={ExpiresIn}"
    )
    return mock_s3, mock_dynamo


# ---------------------------------------------------------------------------
# _decimal_default
# ---------------------------------------------------------------------------

class TestDecimalDefault:
    def test_integer_decimal_returns_int(self):
        assert h._decimal_default(Decimal("100")) == 100

    def test_fractional_decimal_returns_float(self):
        assert h._decimal_default(Decimal("1.5")) == 1.5

    def test_non_decimal_raises_type_error(self):
        with pytest.raises(TypeError):
            h._decimal_default("not a decimal")


# ---------------------------------------------------------------------------
# scan_all
# ---------------------------------------------------------------------------

class TestScanAll:
    def test_single_page(self, mock_aws):
        _, mock_dynamo = mock_aws
        item = make_item("a", "2024-01-01T00:00:00Z")
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [item]}

        result = h.scan_all(mock_table)

        assert result == [item]
        mock_table.scan.assert_called_once_with()

    def test_multiple_pages(self, mock_aws):
        item1 = make_item("a", "2024-01-01T00:00:00Z")
        item2 = make_item("b", "2024-01-02T00:00:00Z")
        mock_table = MagicMock()
        mock_table.scan.side_effect = [
            {"Items": [item1], "LastEvaluatedKey": {"photo_id": "a"}},
            {"Items": [item2]},
        ]

        result = h.scan_all(mock_table)

        assert len(result) == 2
        assert mock_table.scan.call_count == 2
        _, second_kwargs = mock_table.scan.call_args_list[1]
        assert second_kwargs["ExclusiveStartKey"] == {"photo_id": "a"}

    def test_empty_table(self, mock_aws):
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}

        assert h.scan_all(mock_table) == []


# ---------------------------------------------------------------------------
# apply_filters_and_sort
# ---------------------------------------------------------------------------

class TestApplyFiltersAndSort:

    # --- sort by uploaded_at (default) ---

    def test_default_sort_by_uploaded_at_descending(self):
        items = [
            make_item("old", "2024-01-01T00:00:00Z"),
            make_item("new", "2024-03-01T00:00:00Z"),
            make_item("mid", "2024-02-01T00:00:00Z"),
        ]
        result = h.apply_filters_and_sort(items)
        assert [i["photo_id"] for i in result] == ["new", "mid", "old"]

    def test_explicit_sort_by_uploaded_at(self):
        items = [
            make_item("a", "2024-01-01T00:00:00Z"),
            make_item("b", "2024-06-01T00:00:00Z"),
        ]
        result = h.apply_filters_and_sort(items, sort_by="uploaded_at")
        assert result[0]["photo_id"] == "b"

    # --- sort by taken_at ---

    def test_sort_by_taken_at_descending(self):
        items = [
            make_item("early", "2024-01-01T00:00:00Z", taken_at="2023-01-01T00:00:00+00:00"),
            make_item("late",  "2024-01-02T00:00:00Z", taken_at="2023-12-01T00:00:00+00:00"),
            make_item("mid",   "2024-01-03T00:00:00Z", taken_at="2023-06-01T00:00:00+00:00"),
        ]
        result = h.apply_filters_and_sort(items, sort_by="taken_at")
        assert [i["photo_id"] for i in result] == ["late", "mid", "early"]

    def test_sort_by_taken_at_nulls_last(self):
        items = [
            make_item("no_exif", "2024-01-01T00:00:00Z"),
            make_item("has_exif", "2024-01-02T00:00:00Z", taken_at="2023-06-01T00:00:00+00:00"),
        ]
        result = h.apply_filters_and_sort(items, sort_by="taken_at")
        assert result[0]["photo_id"] == "has_exif"
        assert result[-1]["photo_id"] == "no_exif"

    def test_invalid_sort_by_falls_back_to_uploaded_at(self):
        items = [
            make_item("a", "2024-01-01T00:00:00Z"),
            make_item("b", "2024-06-01T00:00:00Z"),
        ]
        result = h.apply_filters_and_sort(items, sort_by="invalid_field")
        assert result[0]["photo_id"] == "b"

    # --- tag filter ---

    def test_filter_by_tag(self):
        items = [
            make_item("landscape_photo", "2024-01-01T00:00:00Z", tags=["landscape"]),
            make_item("portrait_photo",  "2024-01-02T00:00:00Z", tags=["portrait"]),
        ]
        result = h.apply_filters_and_sort(items, tag="landscape")
        assert len(result) == 1
        assert result[0]["photo_id"] == "landscape_photo"

    def test_filter_by_tag_case_insensitive(self):
        items = [make_item("x", "2024-01-01T00:00:00Z", tags=["Landscape"])]
        result = h.apply_filters_and_sort(items, tag="landscape")
        assert len(result) == 1

    def test_filter_no_match_returns_empty(self):
        items = [make_item("x", "2024-01-01T00:00:00Z", tags=["portrait"])]
        result = h.apply_filters_and_sort(items, tag="gps")
        assert result == []

    def test_filter_item_without_tags_field_excluded(self):
        items = [make_item("x", "2024-01-01T00:00:00Z")]  # no tags key
        result = h.apply_filters_and_sort(items, tag="landscape")
        assert result == []

    def test_no_tag_filter_returns_all(self):
        items = [
            make_item("a", "2024-01-01T00:00:00Z", tags=["landscape"]),
            make_item("b", "2024-01-02T00:00:00Z", tags=["portrait"]),
        ]
        result = h.apply_filters_and_sort(items, tag=None)
        assert len(result) == 2

    def test_filter_and_sort_combined(self):
        items = [
            make_item("land_old", "2024-01-01T00:00:00Z", tags=["landscape"]),
            make_item("port",     "2024-01-02T00:00:00Z", tags=["portrait"]),
            make_item("land_new", "2024-03-01T00:00:00Z", tags=["landscape"]),
        ]
        result = h.apply_filters_and_sort(items, sort_by="uploaded_at", tag="landscape")
        assert [i["photo_id"] for i in result] == ["land_new", "land_old"]

    def test_empty_list_returns_empty(self):
        assert h.apply_filters_and_sort([]) == []


# ---------------------------------------------------------------------------
# build_photo_response
# ---------------------------------------------------------------------------

class TestBuildPhotoResponse:
    def test_adds_thumbnail_and_original_urls(self, mock_aws):
        item = make_item("photo1", "2024-01-01T00:00:00Z")
        result = h.build_photo_response(item)
        assert "thumbnail_url" in result
        assert "original_url" in result

    def test_thumbnail_uses_short_ttl(self, mock_aws):
        item = make_item("photo1", "2024-01-01T00:00:00Z")
        result = h.build_photo_response(item)
        assert str(h.THUMBNAIL_URL_TTL) in result["thumbnail_url"]

    def test_original_uses_long_ttl(self, mock_aws):
        item = make_item("photo1", "2024-01-01T00:00:00Z")
        result = h.build_photo_response(item)
        assert str(h.ORIGINAL_URL_TTL) in result["original_url"]

    def test_original_item_fields_preserved(self, mock_aws):
        item = make_item("photo1", "2024-01-01T00:00:00Z")
        result = h.build_photo_response(item)
        assert result["photo_id"] == "photo1"
        assert result["filename"] == "photo1.jpg"


# ---------------------------------------------------------------------------
# handler
# ---------------------------------------------------------------------------

class TestHandler:
    def _make_table(self, mock_aws, items):
        _, mock_dynamo = mock_aws
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": items}
        mock_dynamo.Table.return_value = mock_table
        return mock_table

    def test_options_preflight_returns_200(self, mock_aws):
        response = h.handler({"httpMethod": "OPTIONS"}, None)
        assert response["statusCode"] == 200

    def test_options_includes_cors_headers(self, mock_aws):
        response = h.handler({"httpMethod": "OPTIONS"}, None)
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_get_returns_200(self, mock_aws):
        self._make_table(mock_aws, [])
        response = h.handler({"httpMethod": "GET"}, None)
        assert response["statusCode"] == 200

    def test_get_includes_cors_headers(self, mock_aws):
        self._make_table(mock_aws, [])
        response = h.handler({"httpMethod": "GET"}, None)
        assert "Access-Control-Allow-Origin" in response["headers"]

    def test_body_is_json_list(self, mock_aws):
        self._make_table(mock_aws, [])
        response = h.handler({"httpMethod": "GET"}, None)
        assert isinstance(json.loads(response["body"]), list)

    def test_default_sort_by_uploaded_at_descending(self, mock_aws):
        items = [
            make_item("old", "2024-01-01T00:00:00Z"),
            make_item("new", "2024-03-01T00:00:00Z"),
            make_item("mid", "2024-02-01T00:00:00Z"),
        ]
        self._make_table(mock_aws, items)
        response = h.handler({"httpMethod": "GET"}, None)
        body = json.loads(response["body"])
        assert [p["photo_id"] for p in body] == ["new", "mid", "old"]

    def test_sort_by_taken_at_via_query_param(self, mock_aws):
        items = [
            make_item("early", "2024-01-01T00:00:00Z", taken_at="2023-01-01T00:00:00+00:00"),
            make_item("late",  "2024-01-02T00:00:00Z", taken_at="2023-12-01T00:00:00+00:00"),
        ]
        self._make_table(mock_aws, items)
        response = h.handler(
            {"httpMethod": "GET", "queryStringParameters": {"sort_by": "taken_at"}},
            None,
        )
        body = json.loads(response["body"])
        assert body[0]["photo_id"] == "late"

    def test_tag_filter_via_query_param(self, mock_aws):
        items = [
            make_item("land", "2024-01-01T00:00:00Z", tags=["landscape"]),
            make_item("port", "2024-01-02T00:00:00Z", tags=["portrait"]),
        ]
        self._make_table(mock_aws, items)
        response = h.handler(
            {"httpMethod": "GET", "queryStringParameters": {"tag": "landscape"}},
            None,
        )
        body = json.loads(response["body"])
        assert len(body) == 1
        assert body[0]["photo_id"] == "land"

    def test_missing_query_string_parameters_handled(self, mock_aws):
        self._make_table(mock_aws, [])
        # API Gateway can send queryStringParameters: null
        response = h.handler({"httpMethod": "GET", "queryStringParameters": None}, None)
        assert response["statusCode"] == 200

    def test_decimal_serialized_as_number(self, mock_aws):
        items = [make_item("x", "2024-01-01T00:00:00Z", width=1920, height=1080)]
        self._make_table(mock_aws, items)
        response = h.handler({"httpMethod": "GET"}, None)
        body = json.loads(response["body"])
        assert body[0]["width"] == 1920
        assert body[0]["height"] == 1080

    def test_presigned_urls_in_response(self, mock_aws):
        items = [make_item("x", "2024-01-01T00:00:00Z")]
        self._make_table(mock_aws, items)
        response = h.handler({"httpMethod": "GET"}, None)
        body = json.loads(response["body"])
        assert body[0]["thumbnail_url"].startswith("https://")
        assert body[0]["original_url"].startswith("https://")
