#!/usr/bin/env python3
"""Dry-run scans overviews but does not fetch or write articles."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_ROOT))

from usenet_archiver.cli import pull_group  # noqa: E402
from usenet_archiver.overview import OverviewRow  # noqa: E402


class TestDryRun(unittest.TestCase):
    def test_dry_run_does_not_fetch_or_write(self):
        rows = [
            OverviewRow(
                article_id=10,
                date=datetime(2024, 1, 2, tzinfo=timezone.utc),
                message_id="<a@example.com>",
            ),
            OverviewRow(
                article_id=11,
                date=datetime(2024, 1, 3, tzinfo=timezone.utc),
                message_id="<b@example.com>",
            ),
        ]
        client = mock.Mock()
        client.group.return_value = (1, 100, "211 100 1 100 test.group")
        logger = logging.getLogger("test_dry_run")
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())

        with tempfile.TemporaryDirectory() as td:
            mbox = os.path.join(td, "test.group.mbox")
            completed = os.path.join(td, "completed_newsgroups.log")
            with mock.patch(
                "usenet_archiver.cli.find_articles_in_date_range", return_value=rows
            ) as find_mock, mock.patch(
                "usenet_archiver.cli.fetch_articles_parallel"
            ) as fetch_mock:
                pull_group(
                    client=client,
                    group="test.group",
                    mbox_filename=mbox,
                    start_date=None,
                    end_date=None,
                    overview_chunk=1000,
                    dedup=True,
                    plugins=[],
                    completed_log=completed,
                    logger=logger,
                    conn_kwargs={},
                    dry_run=True,
                )
                find_mock.assert_called_once()
                fetch_mock.assert_not_called()

            self.assertFalse(os.path.exists(mbox))
            self.assertFalse(os.path.exists(completed))


if __name__ == "__main__":
    unittest.main()
