"""
Tests for the pure-Python helpers in job.py.

All Spark / Glue code lives inside main() and is not tested here — it requires
a live Glue runtime.  The parsing helpers are plain Python and cover the vast
majority of the business logic.

Run:
    python -m pytest test_job.py -v
"""

import sys
import unittest

sys.path.insert(0, ".")
from job import make_message_id, parse_date_iso, parse_file, s3_key_from_uri


# ---------------------------------------------------------------------------
# parse_date_iso
# ---------------------------------------------------------------------------

class TestParseDateIso(unittest.TestCase):
    def test_us_short_year(self):
        self.assertEqual(parse_date_iso("1/1/24"), "2024-01-01")

    def test_us_long_year(self):
        self.assertEqual(parse_date_iso("1/1/2024"), "2024-01-01")

    def test_intl_unambiguous(self):
        # 13/1 cannot be MM/DD, so must be DD/MM
        self.assertEqual(parse_date_iso("13/1/24"), "2024-01-13")

    def test_unknown_format_returned_as_is(self):
        self.assertEqual(parse_date_iso("not-a-date"), "not-a-date")

    def test_strips_whitespace(self):
        self.assertEqual(parse_date_iso(" 1/1/24 "), "2024-01-01")

    def test_zero_padded_day_and_month(self):
        self.assertEqual(parse_date_iso("01/01/2024"), "2024-01-01")


# ---------------------------------------------------------------------------
# make_message_id
# ---------------------------------------------------------------------------

class TestMakeMessageId(unittest.TestCase):
    def test_returns_16_char_hex_string(self):
        mid = make_message_id("bronze/whatsapp/chat.txt", 0)
        self.assertEqual(len(mid), 16)
        self.assertRegex(mid, r"^[0-9a-f]{16}$")

    def test_stable_same_inputs(self):
        a = make_message_id("bronze/whatsapp/chat.txt", 42)
        b = make_message_id("bronze/whatsapp/chat.txt", 42)
        self.assertEqual(a, b)

    def test_different_line_index_gives_different_id(self):
        a = make_message_id("bronze/whatsapp/chat.txt", 0)
        b = make_message_id("bronze/whatsapp/chat.txt", 1)
        self.assertNotEqual(a, b)

    def test_different_source_file_gives_different_id(self):
        a = make_message_id("bronze/whatsapp/chat_a.txt", 0)
        b = make_message_id("bronze/whatsapp/chat_b.txt", 0)
        self.assertNotEqual(a, b)


# ---------------------------------------------------------------------------
# s3_key_from_uri
# ---------------------------------------------------------------------------

class TestS3KeyFromUri(unittest.TestCase):
    # urlparse puts the bucket name in netloc, so the returned key is the
    # path component only (no bucket prefix).

    def test_s3_scheme(self):
        uri = "s3://mybucket/bronze/whatsapp/year=2024/month=01/chat.txt"
        self.assertEqual(
            s3_key_from_uri(uri),
            "bronze/whatsapp/year=2024/month=01/chat.txt",
        )

    def test_s3n_scheme(self):
        uri = "s3n://mybucket/bronze/whatsapp/chat.txt"
        self.assertEqual(s3_key_from_uri(uri), "bronze/whatsapp/chat.txt")

    def test_no_leading_slash(self):
        key = s3_key_from_uri("s3://bucket/some/key.txt")
        self.assertFalse(key.startswith("/"))


# ---------------------------------------------------------------------------
# parse_file
# ---------------------------------------------------------------------------

SAMPLE_US = (
    "1/1/24, 10:00 AM - Alice: Hello there!\n"
    "1/1/24, 10:01 AM - Bob: Hi Alice, how are you?\n"
    "1/1/24, 10:02 AM - Alice: Doing great!\n"
    "1/2/24, 09:00 AM - Bob: Good morning!\n"
)

SAMPLE_INTL = (
    "01/01/2024, 10:00 - Alice: Hello!\n"
    "01/01/2024, 10:01 - Bob: Hi!\n"
)

SAMPLE_EN_DASH = (
    "1/1/24, 10:00 AM \u2013 Alice: First message!\n"
    "1/1/24, 10:01 AM \u2013 Bob: Second message!\n"
)

SOURCE = "bronze/whatsapp/year=2024/month=01/chat.txt"


class TestParseFile(unittest.TestCase):

    # --- row count and shape ---

    def test_correct_row_count_us(self):
        rows = parse_file(SOURCE, SAMPLE_US)
        self.assertEqual(len(rows), 4)

    def test_correct_row_count_intl(self):
        rows = parse_file(SOURCE, SAMPLE_INTL)
        self.assertEqual(len(rows), 2)

    def test_empty_content_returns_empty_list(self):
        self.assertEqual(parse_file(SOURCE, ""), [])

    def test_non_whatsapp_returns_empty_list(self):
        self.assertEqual(parse_file(SOURCE, "Just a plain text file.\n"), [])

    def test_each_row_is_7_tuple(self):
        rows = parse_file(SOURCE, SAMPLE_US)
        for row in rows:
            self.assertEqual(len(row), 7)

    # --- column values ---

    def test_date_is_iso_format(self):
        rows = parse_file(SOURCE, SAMPLE_US)
        for row in rows:
            date = row[6]  # date is last (partition column)
            self.assertRegex(date, r"^\d{4}-\d{2}-\d{2}$")

    def test_multiple_dates_preserved(self):
        rows = parse_file(SOURCE, SAMPLE_US)
        dates = {row[6] for row in rows}
        self.assertEqual(len(dates), 2)

    def test_sender_values(self):
        rows = parse_file(SOURCE, SAMPLE_US)
        senders = {row[2] for row in rows}
        self.assertIn("Alice", senders)
        self.assertIn("Bob", senders)

    def test_source_file_set_correctly(self):
        rows = parse_file(SOURCE, SAMPLE_US)
        for row in rows:
            self.assertEqual(row[5], SOURCE)

    def test_message_id_is_16_hex_chars(self):
        rows = parse_file(SOURCE, SAMPLE_US)
        for row in rows:
            self.assertRegex(row[0], r"^[0-9a-f]{16}$")

    def test_message_ids_are_unique_within_file(self):
        rows = parse_file(SOURCE, SAMPLE_US)
        ids = [row[0] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_word_count_is_correct(self):
        rows = parse_file(SOURCE, "1/1/24, 10:00 AM - Alice: one two three\n")
        self.assertEqual(rows[0][4], 3)

    def test_word_count_single_word(self):
        rows = parse_file(SOURCE, "1/1/24, 10:00 AM - Alice: hello\n")
        self.assertEqual(rows[0][4], 1)

    # --- edge cases ---

    def test_message_containing_colon(self):
        rows = parse_file(SOURCE, "1/1/24, 10:00 AM - Alice: Hello: world!\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][3], "Hello: world!")

    def test_en_dash_separator(self):
        rows = parse_file(SOURCE, SAMPLE_EN_DASH)
        self.assertEqual(len(rows), 2)

    def test_international_format(self):
        rows = parse_file(SOURCE, SAMPLE_INTL)
        self.assertTrue(all(row[6] == "2024-01-01" for row in rows))

    def test_same_source_different_lines_get_different_ids(self):
        rows = parse_file(SOURCE, SAMPLE_US)
        ids = [row[0] for row in rows]
        self.assertEqual(len(set(ids)), len(ids))


if __name__ == "__main__":
    unittest.main()
