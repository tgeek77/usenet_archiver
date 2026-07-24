#!/usr/bin/env python3
"""Tests for mbox naming and date-range defaults."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_ROOT))

from usenet_archiver.cli import mbox_name_for, normalize_date_range  # noqa: E402


class TestNormalizeDateRange(unittest.TestCase):
    def test_both_none(self):
        s, e = normalize_date_range(None, None)
        self.assertIsNone(s)
        self.assertIsNone(e)

    def test_start_only_defaults_end_today(self):
        start = datetime(2025, 7, 1)
        s, e = normalize_date_range(start, None, today=date(2025, 7, 10))
        self.assertEqual(s, start)
        self.assertEqual(e, datetime(2025, 7, 10))

    def test_open_ended_differs_by_calendar_day(self):
        """'Since July 1' on July 10 vs July 11 are different windows."""
        start = datetime(2025, 7, 1)
        _, end_10 = normalize_date_range(start, None, today=date(2025, 7, 10))
        _, end_11 = normalize_date_range(start, None, today=date(2025, 7, 11))
        self.assertEqual(end_10.date(), date(2025, 7, 10))
        self.assertEqual(end_11.date(), date(2025, 7, 11))

        g = "alt.fan.usenet"
        name_10 = mbox_name_for(g, None, start, end_10)
        name_11 = mbox_name_for(g, None, start, end_11)
        self.assertEqual(name_10, "alt.fan.usenet-20250701-20250710.mbox")
        self.assertEqual(name_11, "alt.fan.usenet-20250701-20250711.mbox")
        self.assertNotEqual(name_10, name_11)

    def test_end_only_defaults_start(self):
        end = datetime(2022, 6, 1)
        s, e = normalize_date_range(None, end)
        self.assertEqual(s, datetime(1990, 1, 1))
        self.assertEqual(e, end)

    def test_start_after_end_raises(self):
        with self.assertRaises(ValueError):
            normalize_date_range(datetime(2022, 1, 1), datetime(2021, 1, 1))


class TestMboxName(unittest.TestCase):
    def test_dated_windows_are_distinct(self):
        g = "alt.fan.usenet"
        a = mbox_name_for(g, None, datetime(2021, 1, 1), datetime(2022, 1, 1))
        b = mbox_name_for(g, None, datetime(2022, 1, 1), datetime(2023, 1, 1))
        self.assertEqual(a, "alt.fan.usenet-20210101-20220101.mbox")
        self.assertEqual(b, "alt.fan.usenet-20220101-20230101.mbox")
        self.assertNotEqual(a, b)

    def test_undated_is_plain_group_name(self):
        self.assertEqual(
            mbox_name_for("alt.fan.usenet", None, None, None),
            "alt.fan.usenet.mbox",
        )

    def test_explicit_filename_wins(self):
        self.assertEqual(
            mbox_name_for("g", "custom.mbox", datetime(2021, 1, 1), datetime(2022, 1, 1)),
            "custom.mbox",
        )


if __name__ == "__main__":
    unittest.main()
