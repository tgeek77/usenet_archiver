#!/usr/bin/env python3
"""Entry dispatcher: GUI default, -c for CLI subcommands."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestAppDispatch(unittest.TestCase):
    def test_cli_flag_shows_help(self):
        proc = subprocess.run(
            [sys.executable, "-m", "usenet_archiver", "-c", "--help"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": _ROOT},
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.lower()
        self.assertIn("pull", out)
        self.assertIn("list-groups", out)

    def test_pull_help_shows_newsgroup(self):
        proc = subprocess.run(
            [sys.executable, "-m", "usenet_archiver", "-c", "pull", "--help"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": _ROOT},
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("newsgroup", proc.stdout.lower())

    def test_top_level_help_without_c(self):
        proc = subprocess.run(
            [sys.executable, "-m", "usenet_archiver", "--help"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": _ROOT},
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.lower()
        self.assertIn("pull", out)
        self.assertIn("without -c", out)

    def test_top_level_version_without_c(self):
        proc = subprocess.run(
            [sys.executable, "-m", "usenet_archiver", "--version"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": _ROOT},
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("usenet-archiver", proc.stdout.lower())

    def test_cli_pull_missing_server_exits_2(self):
        env = {**os.environ, "PYTHONPATH": _ROOT}
        env.pop("NNTPSERVER", None)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "usenet_archiver",
                "-c",
                "pull",
                "--newsgroup",
                "misc.test",
            ],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr + proc.stdout)

    def test_cli_requires_subcommand(self):
        proc = subprocess.run(
            [sys.executable, "-m", "usenet_archiver", "-c"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": _ROOT},
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("command", (proc.stderr + proc.stdout).lower())

    def test_option_aliases_parse(self):
        from usenet_archiver.cli import build_parser

        args = build_parser().parse_args(
            [
                "pull",
                "-s",
                "news.example.com",
                "--user",
                "alice",
                "--group",
                "news.groups",
                "--start",
                "2024-01-01",
                "--end",
                "2024-02-01",
                "-C",
                "16",
                "-D",
                "64",
                "-t",
                "30",
                "--pass-file",
                "/tmp/pw",
                "-n",
            ]
        )
        self.assertEqual(args.command, "pull")
        self.assertEqual(args.server, "news.example.com")
        self.assertEqual(args.username, "alice")
        self.assertEqual(args.newsgroups, ["news.groups"])
        self.assertEqual(args.start_date, "2024-01-01")
        self.assertEqual(args.end_date, "2024-02-01")
        self.assertEqual(args.connections, 16)
        self.assertEqual(args.pipeline_depth, 64)
        self.assertEqual(args.timeout, 30)
        self.assertEqual(args.password_file, "/tmp/pw")
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    unittest.main()
