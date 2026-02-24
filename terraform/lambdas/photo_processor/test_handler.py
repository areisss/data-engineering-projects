import sys
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from PIL import Image

sys.path.insert(0, ".")
from handler import THUMBNAIL_MAX_PX, get_dimensions, make_thumbnail, handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_image_bytes(width, height, fmt="JPEG", mode="RGB"):
    img = Image.new(mode, (width, height), color=(100, 149, 237))
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _image_size_from_bytes(data: bytes):
    return Image.open(BytesIO(data)).size


def _make_event(bucket, key):
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}


# ---------------------------------------------------------------------------
# get_dimensions
# ---------------------------------------------------------------------------


class TestGetDimensions(unittest.TestCase):
    def test_returns_correct_size(self):
        data = _make_image_bytes(640, 480)
        self.assertEqual(get_dimensions(data), (640, 480))

    def test_square_image(self):
        data = _make_image_bytes(200, 200)
        self.assertEqual(get_dimensions(data), (200, 200))


# ---------------------------------------------------------------------------
# make_thumbnail
# ---------------------------------------------------------------------------


class TestMakeThumbnail(unittest.TestCase):
    def test_landscape_fits_within_max(self):
        data = _make_image_bytes(800, 400)
        thumb = make_thumbnail(data, "JPEG")
        w, h = _image_size_from_bytes(thumb)
        self.assertLessEqual(w, THUMBNAIL_MAX_PX)
        self.assertLessEqual(h, THUMBNAIL_MAX_PX)

    def test_portrait_fits_within_max(self):
        data = _make_image_bytes(400, 800)
        thumb = make_thumbnail(data, "JPEG")
        w, h = _image_size_from_bytes(thumb)
        self.assertLessEqual(w, THUMBNAIL_MAX_PX)
        self.assertLessEqual(h, THUMBNAIL_MAX_PX)

    def test_aspect_ratio_preserved(self):
        # 800x400 is 2:1; thumbnail should stay 2:1
        data = _make_image_bytes(800, 400)
        thumb = make_thumbnail(data, "JPEG")
        w, h = _image_size_from_bytes(thumb)
        self.assertAlmostEqual(w / h, 2.0, delta=0.1)

    def test_small_image_not_enlarged(self):
        data = _make_image_bytes(100, 100)
        thumb = make_thumbnail(data, "JPEG")
        w, h = _image_size_from_bytes(thumb)
        self.assertLessEqual(w, 100)
        self.assertLessEqual(h, 100)

    def test_rgba_converted_for_jpeg(self):
        data = _make_image_bytes(200, 200, fmt="PNG", mode="RGBA")
        # Should not raise when saving as JPEG despite RGBA input
        thumb = make_thumbnail(data, "JPEG")
        self.assertGreater(len(thumb), 0)

    def test_png_stays_png(self):
        data = _make_image_bytes(200, 200, fmt="PNG")
        thumb = make_thumbnail(data, "PNG")
        img = Image.open(BytesIO(thumb))
        self.assertEqual(img.format, "PNG")

    def test_returns_bytes(self):
        data = _make_image_bytes(400, 300)
        self.assertIsInstance(make_thumbnail(data, "JPEG"), bytes)


# ---------------------------------------------------------------------------
# handler
# ---------------------------------------------------------------------------


class TestHandler(unittest.TestCase):
    def setUp(self):
        self._image_data = _make_image_bytes(600, 400)

    @patch("handler.TABLE_NAME", "test-table")
    @patch("handler.BUCKET_NAME", "test-bucket")
    @patch("handler.dynamodb")
    @patch("handler.s3")
    def test_copies_original_and_uploads_thumbnail(self, mock_s3, mock_dynamodb):
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: self._image_data),
            "ContentType": "image/jpeg",
        }

        result = handler(_make_event("test-bucket", "raw-photos/photo.jpg"), None)

        # original copied
        mock_s3.copy_object.assert_called_once_with(
            Bucket="test-bucket",
            CopySource={"Bucket": "test-bucket", "Key": "raw-photos/photo.jpg"},
            Key="photos/originals/photo.jpg",
        )
        # thumbnail uploaded
        mock_s3.put_object.assert_called_once()
        put_kwargs = mock_s3.put_object.call_args[1]
        self.assertEqual(put_kwargs["Key"], "photos/thumbnails/photo.jpg")
        self.assertEqual(put_kwargs["ContentType"], "image/jpeg")

        self.assertEqual(result["statusCode"], 200)

    @patch("handler.TABLE_NAME", "test-table")
    @patch("handler.BUCKET_NAME", "test-bucket")
    @patch("handler.dynamodb")
    @patch("handler.s3")
    def test_writes_dynamodb_record(self, mock_s3, mock_dynamodb):
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: self._image_data),
            "ContentType": "image/jpeg",
        }
        mock_table = mock_dynamodb.Table.return_value

        handler(_make_event("test-bucket", "raw-photos/photo.jpg"), None)

        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        self.assertIn("photo_id", item)
        self.assertEqual(item["original_key"], "photos/originals/photo.jpg")
        self.assertEqual(item["thumbnail_key"], "photos/thumbnails/photo.jpg")
        self.assertEqual(item["filename"], "photo.jpg")
        self.assertEqual(item["width"], 600)
        self.assertEqual(item["height"], 400)
        self.assertEqual(item["size_bytes"], len(self._image_data))
        self.assertIn("uploaded_at", item)

    @patch("handler.TABLE_NAME", "test-table")
    @patch("handler.BUCKET_NAME", "test-bucket")
    @patch("handler.dynamodb")
    @patch("handler.s3")
    def test_url_encoded_key_decoded(self, mock_s3, mock_dynamodb):
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: self._image_data),
            "ContentType": "image/jpeg",
        }

        handler(_make_event("test-bucket", "raw-photos/my%20photo.jpg"), None)

        call_kwargs = mock_s3.copy_object.call_args[1]
        self.assertEqual(
            call_kwargs["CopySource"]["Key"], "raw-photos/my photo.jpg"
        )

    @patch("handler.TABLE_NAME", "test-table")
    @patch("handler.BUCKET_NAME", "test-bucket")
    @patch("handler.dynamodb")
    @patch("handler.s3")
    def test_png_image_handled(self, mock_s3, mock_dynamodb):
        png_data = _make_image_bytes(400, 400, fmt="PNG")
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: png_data),
            "ContentType": "image/png",
        }

        result = handler(_make_event("test-bucket", "raw-photos/image.png"), None)

        self.assertEqual(result["statusCode"], 200)
        put_kwargs = mock_s3.put_object.call_args[1]
        self.assertEqual(put_kwargs["Key"], "photos/thumbnails/image.png")

    @patch("handler.TABLE_NAME", "test-table")
    @patch("handler.BUCKET_NAME", "test-bucket")
    @patch("handler.dynamodb")
    @patch("handler.s3")
    def test_multiple_records_processed(self, mock_s3, mock_dynamodb):
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: self._image_data),
            "ContentType": "image/jpeg",
        }
        event = {
            "Records": [
                {"s3": {"bucket": {"name": "b"}, "object": {"key": "raw-photos/a.jpg"}}},
                {"s3": {"bucket": {"name": "b"}, "object": {"key": "raw-photos/b.jpg"}}},
            ]
        }

        handler(event, None)

        self.assertEqual(mock_s3.copy_object.call_count, 2)
        self.assertEqual(mock_s3.put_object.call_count, 2)
        self.assertEqual(mock_dynamodb.Table.return_value.put_item.call_count, 2)


if __name__ == "__main__":
    unittest.main()
