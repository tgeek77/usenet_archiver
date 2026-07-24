#!/usr/bin/env python3
"""Tests for mboxrd writing and Message-ID dedup."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_ROOT))

from usenet_archiver.mboxout import (  # noqa: E402
    MboxWriter,
    escape_mboxrd,
    format_envelope_utc,
    index_message_ids,
    write_mbox_message,
)


class TestEscape(unittest.TestCase):
    def test_escape_from_line(self):
        data = b"Header: x\n\nFrom someone\nbody\n"
        out = escape_mboxrd(data)
        self.assertIn(b">From someone\n", out)
        self.assertNotIn(b"\nFrom someone\n", out)

    def test_already_escaped(self):
        data = b">From already\n"
        out = escape_mboxrd(data)
        self.assertEqual(out.count(b">From"), 1)


class TestEnvelope(unittest.TestCase):
    def test_locale_independent(self):
        dt = datetime(2020, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        line = format_envelope_utc(dt, "user@example.com")
        self.assertTrue(line.startswith(b"From user@example.com "))
        self.assertIn(b"Wed", line)  # 2020-01-15 was a Wednesday
        self.assertIn(b"Jan", line)
        self.assertIn(b"2020", line)
        # Must be ASCII
        line.decode("ascii")


class TestDedup(unittest.TestCase):
    def test_index_and_skip(self):
        article1 = (
            b"From: a@x\nMessage-ID: <one@ex.com>\nDate: Wed, 15 Jan 2020 12:00:00 +0000\n"
            b"Subject: One\n\nBody one\n"
        )
        article2 = (
            b"From: b@x\nMessage-ID: <two@ex.com>\nDate: Wed, 15 Jan 2020 13:00:00 +0000\n"
            b"Subject: Two\n\nBody two\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.mbox")
            with MboxWriter(path, dedup=True) as w:
                self.assertTrue(w.write(article1))
                self.assertTrue(w.write(article2))
                self.assertFalse(w.write(article1))  # dup
                self.assertEqual(w.written, 2)
                self.assertEqual(w.skipped_dup, 1)

            ids = index_message_ids(path)
            self.assertIn("<one@ex.com>", ids)
            self.assertIn("<two@ex.com>", ids)

            # Re-open append: dups still skipped
            with MboxWriter(path, dedup=True) as w:
                self.assertFalse(w.write(article1))
                self.assertEqual(w.skipped_dup, 1)

    def test_append_does_not_truncate(self):
        article1 = b"From: a@x\nMessage-ID: <a@ex.com>\nSubject: A\n\nA\n"
        article2 = b"From: b@x\nMessage-ID: <b@ex.com>\nSubject: B\n\nB\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.mbox")
            with MboxWriter(path, dedup=True) as w:
                w.write(article1)
            size1 = os.path.getsize(path)
            with MboxWriter(path, dedup=True) as w:
                w.write(article2)
            size2 = os.path.getsize(path)
            self.assertGreater(size2, size1)


class TestWriteMessage(unittest.TestCase):
    def test_roundtrip_bytes(self):
        # Include non-ASCII ISO-8859-1 byte in body
        article = (
            b"From: =?iso-8859-1?q?J=F6rg?= <j@ex.com>\n"
            b"Message-ID: <caf\xe9@ex.com>\n"
            b"Subject: Test\n\n"
            b"caf\xe9 au lait\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.mbox")
            with open(path, "wb") as fh:
                write_mbox_message(fh, article)
            with open(path, "rb") as fh:
                data = fh.read()
            self.assertIn(b"caf\xe9 au lait", data)
            self.assertTrue(data.startswith(b"From "))


if __name__ == "__main__":
    unittest.main()
