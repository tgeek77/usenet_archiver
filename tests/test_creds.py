#!/usr/bin/env python3
"""Tests for credential and server resolution."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_ROOT))

from usenet_archiver.creds import get_default_nntp_server, resolve_credentials, split_host  # noqa: E402


class TestSplitHost(unittest.TestCase):
    def test_host_only(self):
        h, p = split_host("news.example.com")
        self.assertEqual(h, "news.example.com")
        self.assertIsNone(p)

    def test_host_port(self):
        h, p = split_host("news.example.com:563")
        self.assertEqual(h, "news.example.com")
        self.assertEqual(p, 563)

    def test_ipv6(self):
        h, p = split_host("[::1]:119")
        self.assertEqual(h, "::1")
        self.assertEqual(p, 119)

    def test_default_port(self):
        h, p = split_host("news.example.com", default_port=563)
        self.assertEqual(p, 563)


class TestResolve(unittest.TestCase):
    def test_explicit_wins(self):
        ep = resolve_credentials(
            server="news.example.com:119",
            port=None,
            username="u",
            password="p",
            use_netrc=False,
            use_ssl=True,
        )
        self.assertEqual(ep.host, "news.example.com")
        self.assertEqual(ep.port, 119)
        self.assertEqual(ep.username, "u")
        self.assertEqual(ep.password, "p")

    def test_ssl_default_port(self):
        ep = resolve_credentials(
            server="news.example.com",
            port=None,
            username=None,
            password=None,
            use_netrc=False,
            use_ssl=True,
        )
        self.assertEqual(ep.port, 563)

    def test_password_file_over_env(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            fh.write("filepass\n")
            path = fh.name
        try:
            with mock.patch.dict(os.environ, {"NNTP_PASSWORD": "envpass"}):
                ep = resolve_credentials(
                    server="news.example.com",
                    port=563,
                    username="u",
                    password=None,
                    password_file=path,
                    use_netrc=False,
                )
            self.assertEqual(ep.password, "filepass")
        finally:
            os.unlink(path)

    def test_env_password(self):
        with mock.patch.dict(os.environ, {"NNTP_PASSWORD": "envpass"}):
            ep = resolve_credentials(
                server="news.example.com",
                port=563,
                username="u",
                password=None,
                use_netrc=False,
            )
        self.assertEqual(ep.password, "envpass")

    def test_explicit_password_over_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            fh.write("filepass\n")
            path = fh.name
        try:
            ep = resolve_credentials(
                server="news.example.com",
                port=563,
                username="u",
                password="flagpass",
                password_file=path,
                use_netrc=False,
            )
            self.assertEqual(ep.password, "flagpass")
        finally:
            os.unlink(path)

    def test_nntpserver_env(self):
        with mock.patch.dict(os.environ, {"NNTPSERVER": "from.env.example"}):
            self.assertEqual(get_default_nntp_server(), "from.env.example")
            ep = resolve_credentials(
                server=None,
                port=None,
                username=None,
                password=None,
                use_netrc=False,
                use_ssl=False,
            )
            self.assertEqual(ep.host, "from.env.example")
            self.assertEqual(ep.port, 119)

    def test_missing_server_exits_2(self):
        env = {k: v for k, v in os.environ.items() if k != "NNTPSERVER"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("usenet_archiver.creds.open", side_effect=OSError("no file")):
                with self.assertRaises(SystemExit) as cm:
                    resolve_credentials(
                        server=None,
                        port=None,
                        username=None,
                        password=None,
                        use_netrc=False,
                    )
                self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
