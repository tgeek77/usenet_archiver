#!/usr/bin/env python3
"""Tests for archiving policy (server blacklist + binary groups)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_ROOT))

from usenet_archiver.creds import resolve_credentials  # noqa: E402
from usenet_archiver.policy import (  # noqa: E402
    BLOCKED_SERVER_MESSAGE,
    check_server_allowed,
    filter_group_specs,
    is_binary_newsgroup,
    is_server_blacklisted,
    read_groups_file,
)


class TestServerBlacklist(unittest.TestCase):
    def test_eternal_september_hosts(self):
        for host in (
            "news.eternal-september.org",
            "reader80.eternal-september.org",
            "reader443.eternal-september.org",
            "eternal-september.org",
            "NEWS.Eternal-September.ORG",
            "foo.eternal-september.org",
        ):
            self.assertTrue(is_server_blacklisted(host), host)

    def test_allowed_host(self):
        self.assertFalse(is_server_blacklisted("news.example.com"))

    def test_check_raises_message(self):
        with self.assertRaises(ValueError) as ctx:
            check_server_allowed("news.eternal-september.org")
        self.assertEqual(str(ctx.exception), BLOCKED_SERVER_MESSAGE)

    def test_resolve_credentials_blocks(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_credentials(
                server="news.eternal-september.org",
                port=563,
                username="u",
                password="p",
                use_netrc=False,
            )
        self.assertEqual(str(ctx.exception), BLOCKED_SERVER_MESSAGE)


class TestBinaryGroups(unittest.TestCase):
    def test_binary_names(self):
        for name in (
            "alt.binaries.warez",
            "alt.bainary.foo",
            "de.binaries.misc",
            "fr.binaire.test",
            "es.binarios.foo",
        ):
            self.assertTrue(is_binary_newsgroup(name), name)

    def test_text_groups_allowed(self):
        for name in ("comp.lang.python", "news.groups", "alt.fan.usenet"):
            self.assertFalse(is_binary_newsgroup(name), name)

    def test_filter_specs(self):
        kept, skipped = filter_group_specs(
            [
                ("comp.lang.python", None),
                ("alt.binaries.foo", "x.mbox"),
                ("news.groups", None),
            ]
        )
        self.assertEqual([g for g, _ in kept], ["comp.lang.python", "news.groups"])
        self.assertEqual(skipped, ["alt.binaries.foo"])


class TestReadGroupsFile(unittest.TestCase):
    def test_one_per_line(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            fh.write("# comment\n\ncomp.lang.python\nalt.fan.usenet\n")
            path = fh.name
        try:
            self.assertEqual(
                read_groups_file(path),
                ["comp.lang.python", "alt.fan.usenet"],
            )
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
