#!/usr/bin/env python3
"""Entry dispatcher: GUI default, -c for CLI."""

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
        self.assertIn("newsgroup", proc.stdout.lower())

    def test_cli_flag_missing_server_exits_2(self):
        env = {**os.environ, "PYTHONPATH": _ROOT}
        env.pop("NNTPSERVER", None)
        proc = subprocess.run(
            [sys.executable, "-m", "usenet_archiver", "-c", "--newsgroup", "misc.test"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main()
