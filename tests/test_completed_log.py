#!/usr/bin/env python3
"""completed_newsgroups.log is only written after a successful pull."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from usenet_archiver.cli import mark_completed


class TestMarkCompleted(unittest.TestCase):
    def test_appends_job_name(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "completed_newsgroups.log")
            log = logging.getLogger("test_completed")
            mark_completed(path, "alt.fan.usenet.mbox", log)
            mark_completed(path, "alt.test-20250101-20250131.mbox", log)
            with open(path, encoding="utf-8") as fh:
                lines = [ln.strip() for ln in fh if ln.strip()]
            self.assertEqual(
                lines,
                ["alt.fan.usenet.mbox", "alt.test-20250101-20250131.mbox"],
            )


if __name__ == "__main__":
    unittest.main()
