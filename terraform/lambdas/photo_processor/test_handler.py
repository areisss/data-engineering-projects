import sys
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from PIL import Image

sys.path.insert(0, ".")
from handler import THUMBNAIL_MAX_PX, get_dimensions, make_thumbnail, extract_exif, handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_image_bytes(width, height, fmt="JPEG", mode="RGB"):
    img = Image.new(mode, (width, height), color=(100, 149, 237))
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _make_image_bytes_with_exif(width, height, make=None, model=None,
                                 datetime_original=None, flash=None):
    """Create JPEG bytes with EXIF data embedded via Pillow."""
    img = Image.new("RGB", (width, height), color=(100, 149, 237))
    exif = img.getexif()
    if make:
        exif[271] = make
    if model:
        exif[272] = model
    if datetime_original:
        exif[36867] = datetime_original
    if flash is not None:
        exif[37385] = flash
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
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
# extract_exif
# ---------------------------------------------------------------------------


class TestExtractExif(unittest.TestCase):

    # --- no EXIF (plain synthesised image) ---

    def test_no_exif_returns_none_fields(self):
        data = _make_image_bytes(400, 300)
        result = extract_exif(data)
        self.assertIsNone(result["taken_at"])
        self.assertIsNone(result["camera_make"])
        self.assertIsNone(result["camera_model"])

    def test_no_exif_still_derives_orientation_tag(self):
        # Landscape
        self.assertIn("landscape", extract_exif(_make_image_bytes(800, 400))["tags"])
        # Portrait
        self.assertIn("portrait", extract_exif(_make_image_bytes(400, 800))["tags"])
        # Square
        self.assertIn("square", extract_exif(_make_image_bytes(200, 200))["tags"])

    # --- EXIF present ---

    def test_reads_camera_make_and_model(self):
        data = _make_image_bytes_with_exif(400, 300, make="Apple", model="iPhone 15")
        result = extract_exif(data)
        self.assertEqual(result["camera_make"], "Apple")
        self.assertEqual(result["camera_model"], "iPhone 15")

    def test_reads_taken_at_as_iso8601(self):
        data = _make_image_bytes_with_exif(400, 300, datetime_original="2024:03:15 10:30:00")
        result = extract_exif(data)
        self.assertEqual(result["taken_at"], "2024-03-15T10:30:00+00:00")

    def test_flash_tag_added_when_flash_fired(self):
        data = _make_image_bytes_with_exif(400, 300, flash=1)  # bit 0 set = fired
        self.assertIn("flash", extract_exif(data)["tags"])

    def test_flash_tag_absent_when_flash_not_fired(self):
        data = _make_image_bytes_with_exif(400, 300, flash=0)
        self.assertNotIn("flash", extract_exif(data)["tags"])

    def test_flash_tag_absent_when_flash_exif_missing(self):
        data = _make_image_bytes_with_exif(400, 300)  # no flash field
        self.assertNotIn("flash", extract_exif(data)["tags"])

    def test_gps_tag_added_when_gps_present(self):
        # Pillow can't serialise a synthetic GPS sub-IFD, so patch at Image.open.
        data = _make_image_bytes(400, 300)
        mock_exif = MagicMock()
        mock_exif.get = lambda tag: {34853: {"1": "N"}}.get(tag)  # truthy GPS entry
        mock_img = MagicMock()
        mock_img.size = (400, 300)
        mock_img.getexif.return_value = mock_exif
        with patch("handler.Image.open", return_value=mock_img):
            result = extract_exif(data)
        self.assertIn("gps", result["tags"])

    def test_gps_tag_absent_when_no_gps(self):
        data = _make_image_bytes_with_exif(400, 300)
        self.assertNotIn("gps", extract_exif(data)["tags"])

    def test_orientation_tag_present_with_exif(self):
        data = _make_image_bytes_with_exif(800, 600, make="Canon")
        self.assertIn("landscape", extract_exif(data)["tags"])

    # --- edge cases ---

    def test_corrupt_bytes_returns_defaults(self):
        result = extract_exif(b"not-an-image")
        self.assertIsNone(result["taken_at"])
        self.assertIsNone(result["camera_make"])
        self.assertIsNone(result["camera_model"])
        self.assertEqual(result["tags"], [])

    def test_invalid_datetime_string_ignored(self):
        data = _make_image_bytes_with_exif(400, 300, datetime_original="not-a-date")
        result = extract_exif(data)
        self.assertIsNone(result["taken_at"])

    def test_returns_dict_with_expected_keys(self):
        data = _make_image_bytes(400, 300)
        result = extract_exif(data)
        self.assertIn("taken_at", result)
        self.assertIn("camera_make", result)
        self.assertIn("camera_model", result)
        self.assertIn("tags", result)

    def test_tags_is_always_a_list(self):
        self.assertIsInstance(extract_exif(_make_image_bytes(400, 300))["tags"], list)
        self.assertIsInstance(extract_exif(b"garbage")["tags"], list)


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
    def test_writes_dynamodb_record_with_base_fields(self, mock_s3, mock_dynamodb):
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
    def test_writes_exif_fields_to_dynamo(self, mock_s3, mock_dynamodb):
        """EXIF fields are written to DynamoDB when present in the image."""
        exif_image = _make_image_bytes_with_exif(
            600, 400,
            make="Sony",
            model="A7 IV",
            datetime_original="2024:06:01 08:00:00",
        )
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: exif_image),
            "ContentType": "image/jpeg",
        }
        mock_table = mock_dynamodb.Table.return_value

        handler(_make_event("test-bucket", "raw-photos/photo.jpg"), None)

        item = mock_table.put_item.call_args[1]["Item"]
        self.assertEqual(item["camera_make"], "Sony")
        self.assertEqual(item["camera_model"], "A7 IV")
        self.assertEqual(item["taken_at"], "2024-06-01T08:00:00+00:00")
        self.assertIn("tags", item)
        self.assertIn("landscape", item["tags"])

    @patch("handler.TABLE_NAME", "test-table")
    @patch("handler.BUCKET_NAME", "test-bucket")
    @patch("handler.dynamodb")
    @patch("handler.s3")
    def test_none_exif_fields_omitted_from_dynamo(self, mock_s3, mock_dynamodb):
        """None EXIF fields are stripped before writing to DynamoDB."""
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: self._image_data),
            "ContentType": "image/jpeg",
        }
        mock_table = mock_dynamodb.Table.return_value

        handler(_make_event("test-bucket", "raw-photos/photo.jpg"), None)

        item = mock_table.put_item.call_args[1]["Item"]
        # Plain synthesised image has no DateTimeOriginal/Make/Model
        self.assertNotIn("taken_at", item)
        self.assertNotIn("camera_make", item)
        self.assertNotIn("camera_model", item)
        # tags list is still present (orientation is always derived)
        self.assertIn("tags", item)

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
