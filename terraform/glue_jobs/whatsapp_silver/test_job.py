import sys
import unittest

import pandas as pd

sys.path.insert(0, ".")
from job import parse_chat, parse_date_iso

SAMPLE_CHAT_US = (
    "1/1/24, 10:00 AM - Alice: Hello there!\n"
    "1/1/24, 10:01 AM - Bob: Hi Alice, how are you?\n"
    "1/1/24, 10:02 AM - Alice: Doing great!\n"
    "1/2/24, 09:00 AM - Bob: Good morning!\n"
)

SAMPLE_CHAT_INTL = (
    "01/01/2024, 10:00 - Alice: Hello!\n"
    "01/01/2024, 10:01 - Bob: Hi!\n"
)

NOT_WHATSAPP = "Just a plain text file.\nNo timestamps here.\n"


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


class TestParseChat(unittest.TestCase):
    def test_correct_row_count(self):
        df = parse_chat(SAMPLE_CHAT_US)
        self.assertEqual(len(df), 4)

    def test_column_names(self):
        df = parse_chat(SAMPLE_CHAT_US)
        self.assertListEqual(list(df.columns), ["date", "time", "sender", "message"])

    def test_correct_senders(self):
        df = parse_chat(SAMPLE_CHAT_US)
        self.assertIn("Alice", df["sender"].values)
        self.assertIn("Bob", df["sender"].values)

    def test_date_is_iso_format(self):
        df = parse_chat(SAMPLE_CHAT_US)
        self.assertTrue(all(df["date"].str.match(r"\d{4}-\d{2}-\d{2}")))

    def test_multiple_dates_preserved(self):
        df = parse_chat(SAMPLE_CHAT_US)
        self.assertEqual(len(df["date"].unique()), 2)

    def test_international_format(self):
        df = parse_chat(SAMPLE_CHAT_INTL)
        self.assertEqual(len(df), 2)
        self.assertTrue(all(df["date"] == "2024-01-01"))

    def test_empty_content_returns_empty_dataframe(self):
        df = parse_chat("")
        self.assertTrue(df.empty)
        self.assertListEqual(list(df.columns), ["date", "time", "sender", "message"])

    def test_non_whatsapp_returns_empty_dataframe(self):
        df = parse_chat(NOT_WHATSAPP)
        self.assertTrue(df.empty)

    def test_message_containing_colon(self):
        content = "1/1/24, 10:00 AM - Alice: Hello: world!\n"
        df = parse_chat(content)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["message"], "Hello: world!")

    def test_en_dash_separator(self):
        content = "1/1/24, 10:00 AM \u2013 Alice: Hi!\n1/1/24, 10:01 AM \u2013 Bob: Hey!\n"
        df = parse_chat(content)
        self.assertEqual(len(df), 2)


if __name__ == "__main__":
    unittest.main()
