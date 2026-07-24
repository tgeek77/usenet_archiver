#!/usr/bin/env python3
"""Tests for plugin parsing and mutation."""

from __future__ import annotations

import email
import os
import sys
import unittest

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_ROOT))

from usenet_archiver.plugins import apply_plugins, keep_headers, mimify, parse_plugin_spec, strip_headers  # noqa: E402


def _msg():
    return email.message_from_bytes(
        b"From: a@x\nTo: b@x\nCc: c@x\nSubject: Hi\n"
        b"Message-ID: <m@x>\nContent-Type: text/plain\n\nBody\n"
    )


class TestParseSpec(unittest.TestCase):
    def test_simple(self):
        fn = parse_plugin_spec("strip_headers")
        msg = _msg()
        out = fn(message=msg)
        self.assertNotIn("To", out)
        self.assertNotIn("Cc", out)
        self.assertIn("Subject", out)

    def test_positional(self):
        fn = parse_plugin_spec("strip_headers:Subject")
        msg = _msg()
        out = fn(message=msg)
        self.assertNotIn("Subject", out)
        self.assertIn("To", out)

    def test_kwargs(self):
        fn = parse_plugin_spec("mimify:type=text/html:charset=UTF-8")
        msg = email.message_from_bytes(b"From: a@x\nSubject: x\n\nBody\n")
        out = fn(message=msg)
        self.assertIn("text/html", out["Content-Type"])
        self.assertIn("UTF-8", out["Content-Type"])

    def test_unknown(self):
        with self.assertRaises(ValueError):
            parse_plugin_spec("nope")


class TestPlugins(unittest.TestCase):
    def test_mimify_skips_existing(self):
        msg = _msg()
        out = mimify(message=msg)
        self.assertEqual(out["Content-Type"], "text/plain")

    def test_keep_headers(self):
        msg = _msg()
        out = keep_headers(headers="From,Subject", message=msg)
        self.assertIn("From", out)
        self.assertIn("Subject", out)
        self.assertNotIn("To", out)
        self.assertEqual(out.get_payload(), "")

    def test_apply_drop(self):
        def drop(message=None):
            return None

        msg = _msg()
        self.assertIsNone(apply_plugins(msg, [drop]))

    def test_chain(self):
        msg = _msg()
        plugins = [parse_plugin_spec("strip_headers"), parse_plugin_spec("mimify")]
        out = apply_plugins(msg, plugins)
        self.assertIsNotNone(out)
        self.assertNotIn("To", out)


if __name__ == "__main__":
    unittest.main()
