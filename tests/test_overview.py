#!/usr/bin/env python3
"""Tests for overview date bisect and chunk scanning."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_ROOT))

from usenet_archiver.overview import (  # noqa: E402
    OverviewRow,
    bisect_lower,
    bisect_upper,
    filter_rows_by_dedup,
    parse_overview_line,
)


def _row(aid: int, year: int, month: int = 1, day: int = 15, mid: str = "") -> OverviewRow:
    return OverviewRow(
        article_id=aid,
        date=datetime(year, month, day, tzinfo=timezone.utc),
        message_id=mid or f"<art{aid}@example.com>",
    )


class FakeOverviewStore:
    """In-memory overview for testing bisect/scan without a network."""

    def __init__(self, rows):
        self.by_id = {r.article_id: r for r in rows}
        self.calls = []

    def fetch(self, start_id, end_id):
        self.calls.append((start_id, end_id))
        return [self.by_id[i] for i in range(start_id, end_id + 1) if i in self.by_id]


class TestParseOverview(unittest.TestCase):
    def test_parse_standard_line(self):
        line = (
            b"42\tHello\tuser@ex.com\t"
            b"Mon, 01 Jan 2020 12:00:00 +0000\t"
            b"<id42@ex.com>\t\t100\t5"
        )
        row = parse_overview_line(line)
        self.assertIsNotNone(row)
        self.assertEqual(row.article_id, 42)
        self.assertEqual(row.subject, "Hello")
        self.assertEqual(row.message_id, "<id42@ex.com>")
        self.assertEqual(row.date.year, 2020)

    def test_parse_invalid(self):
        self.assertIsNone(parse_overview_line(b"not-a-number\tfoo"))


class TestBisect(unittest.TestCase):
    def setUp(self):
        # IDs 1..100 with dates spanning 2010-01 through 2018-04 roughly monthly
        rows = []
        for i in range(1, 101):
            year = 2010 + (i - 1) // 12
            month = ((i - 1) % 12) + 1
            rows.append(_row(i, year, month, 10))
        self.store = FakeOverviewStore(rows)
        self.first, self.last = 1, 100

    def test_bisect_lower(self):
        target = datetime(2015, 1, 1).date()
        aid = bisect_lower(self.store.fetch, self.first, self.last, target)
        # Article for 2015-01 is id 61 ((2015-2010)*12+1)
        self.assertGreaterEqual(aid, 55)
        self.assertLessEqual(aid, 65)

    def test_bisect_upper(self):
        target = datetime(2012, 6, 30).date()
        aid = bisect_upper(self.store.fetch, self.first, self.last, target)
        self.assertGreaterEqual(aid, 25)
        self.assertLessEqual(aid, 40)

    def test_gaps(self):
        # Remove some mid-range articles
        for i in range(40, 50):
            del self.store.by_id[i]
        target = datetime(2013, 1, 1).date()
        aid = bisect_lower(self.store.fetch, self.first, self.last, target)
        self.assertIsInstance(aid, int)


class TestNonMonotonic(unittest.TestCase):
    def test_out_of_order_date_still_found_by_scan(self):
        from usenet_archiver.overview import _scan_chunks

        rows = [
            _row(1, 2020),
            _row(2, 2021),
            _row(3, 2019),  # backdated
            _row(4, 2022),
        ]
        store = FakeOverviewStore(rows)
        start_d = datetime(2020, 1, 1).date()
        end_d = datetime(2021, 12, 31).date()
        matched = _scan_chunks(store.fetch, 1, 4, 10, start_d, end_d)
        ids = {r.article_id for r in matched}
        self.assertIn(1, ids)
        self.assertIn(2, ids)
        # 2019 article filtered out; 2022 filtered out
        self.assertNotIn(3, ids)
        self.assertNotIn(4, ids)


class TestDedupFilter(unittest.TestCase):
    def test_filter(self):
        rows = [_row(1, 2020, mid="<a@x>"), _row(2, 2020, mid="<b@x>")]
        out = filter_rows_by_dedup(rows, {"<a@x>"})
        self.assertEqual([r.article_id for r in out], [2])


if __name__ == "__main__":
    unittest.main()
