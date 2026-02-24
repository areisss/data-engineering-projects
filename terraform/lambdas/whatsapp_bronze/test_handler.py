import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")
from handler import bronze_key, handler, is_whatsapp_export

SAMPLE_WHATSAPP_US = (
    "1/1/24, 10:00 AM - Alice: Hello there!\n"
    "1/1/24, 10:01 AM - Bob: Hi Alice!\n"
    "1/1/24, 10:02 AM - Alice: Great!\n"
)

SAMPLE_WHATSAPP_INTL = (
    "01/01/2024, 10:00 - Alice: Hello there!\n"
    "01/01/2024, 10:01 - Bob: Hi Alice!\n"
    "01/01/2024, 10:02 - Alice: Great!\n"
)

SAMPLE_NOT_WHATSAPP = (
    "This is just a regular text file.\n"
    "No WhatsApp formatting here.\n"
)


class TestIsWhatsappExport(unittest.TestCase):
    def test_us_date_format(self):
        self.assertTrue(is_whatsapp_export(SAMPLE_WHATSAPP_US))

    def test_international_date_format(self):
        self.assertTrue(is_whatsapp_export(SAMPLE_WHATSAPP_INTL))

    def test_non_whatsapp_file(self):
        self.assertFalse(is_whatsapp_export(SAMPLE_NOT_WHATSAPP))

    def test_empty_string(self):
        self.assertFalse(is_whatsapp_export(""))

    def test_requires_at_least_two_matches(self):
        self.assertFalse(
            is_whatsapp_export("1/1/24, 10:00 AM - Alice: Hello\nrandom line\n")
        )


class TestBronzeKey(unittest.TestCase):
    def test_partition_format(self):
        ts = datetime(2024, 3, 5, tzinfo=timezone.utc)
        self.assertEqual(
            bronze_key("chat.txt", ts),
            "bronze/whatsapp/year=2024/month=03/chat.txt",
        )

    def test_single_digit_month_is_zero_padded(self):
        ts = datetime(2024, 1, 15, tzinfo=timezone.utc)
        self.assertIn("month=01", bronze_key("export.txt", ts))

    def test_uses_current_time_when_ts_omitted(self):
        key = bronze_key("chat.txt")
        self.assertTrue(key.startswith("bronze/whatsapp/year="))
        self.assertIn("/month=", key)
        self.assertTrue(key.endswith("/chat.txt"))


class TestHandler(unittest.TestCase):
    def _make_event(self, bucket, key):
        return {
            "Records": [
                {"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}
            ]
        }

    @patch("handler.s3")
    def test_valid_file_is_copied_to_bronze(self, mock_s3):
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: SAMPLE_WHATSAPP_US.encode())
        }

        result = handler(
            self._make_event("my-bucket", "raw-whatsapp-uploads/chat.txt"), None
        )

        mock_s3.copy_object.assert_called_once()
        kwargs = mock_s3.copy_object.call_args[1]
        self.assertEqual(kwargs["Bucket"], "my-bucket")
        self.assertEqual(
            kwargs["CopySource"],
            {"Bucket": "my-bucket", "Key": "raw-whatsapp-uploads/chat.txt"},
        )
        self.assertTrue(kwargs["Key"].startswith("bronze/whatsapp/year="))
        self.assertTrue(kwargs["Key"].endswith("/chat.txt"))
        self.assertEqual(result["statusCode"], 200)

    @patch("handler.s3")
    def test_invalid_file_is_not_copied(self, mock_s3):
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: SAMPLE_NOT_WHATSAPP.encode())
        }

        handler(
            self._make_event("my-bucket", "raw-whatsapp-uploads/notes.txt"), None
        )

        mock_s3.copy_object.assert_not_called()

    @patch("handler.s3")
    def test_url_encoded_key_is_decoded(self, mock_s3):
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: SAMPLE_WHATSAPP_US.encode())
        }

        handler(
            self._make_event("my-bucket", "raw-whatsapp-uploads/my%20chat.txt"), None
        )

        kwargs = mock_s3.copy_object.call_args[1]
        self.assertEqual(
            kwargs["CopySource"]["Key"], "raw-whatsapp-uploads/my chat.txt"
        )

    @patch("handler.s3")
    def test_multiple_records_all_processed(self, mock_s3):
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: SAMPLE_WHATSAPP_US.encode())
        }

        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "raw-whatsapp-uploads/a.txt"},
                    }
                },
                {
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "raw-whatsapp-uploads/b.txt"},
                    }
                },
            ]
        }
        handler(event, None)
        self.assertEqual(mock_s3.copy_object.call_count, 2)


if __name__ == "__main__":
    unittest.main()
