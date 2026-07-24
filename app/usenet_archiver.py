#!/usr/bin/env python3
"""Back-compat shim: ``python3 app/usenet_archiver.py`` → package CLI."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from usenet_archiver.cli import run

if __name__ == "__main__":
    run()
