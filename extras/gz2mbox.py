#!/usr/bin/env python3
"""Decompress .gz archives containing Usenet articles into a single mbox file.

Shares mboxrd escaping and envelope helpers with app/mboxout.py when available;
falls back to local copies when run standalone from extras/.
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
from pathlib import Path
from typing import BinaryIO, List, Optional

ARTICLE_SPLIT_RE = re.compile(rb"\n(?=Path: )")

# Prefer shared helpers from the archiver package.
_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if _APP_DIR.is_dir() and str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

try:
    from mboxout import escape_mboxrd, write_mbox_message  # type: ignore
except ImportError:
    # Standalone fallback (locale-independent envelope).
    import email
    from datetime import datetime, timezone
    from email.utils import parseaddr, parsedate_to_datetime

    _WDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    _MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

    def escape_mboxrd(data: bytes) -> bytes:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        lines = data.split(b"\n")
        escaped = []
        for line in lines:
            if line.startswith(b"From ") and not line.startswith(b">From "):
                escaped.append(b">" + line)
            else:
                escaped.append(line)
        result = b"\n".join(escaped)
        if result and not result.endswith(b"\n"):
            result += b"\n"
        return result

    def write_mbox_message(handle: BinaryIO, article: bytes, dt=None) -> None:
        msg = email.message_from_bytes(article)
        if dt is None:
            date_hdr = msg.get("Date")
            if date_hdr:
                try:
                    dt = parsedate_to_datetime(date_hdr)
                except (TypeError, ValueError, OverflowError):
                    dt = None
        if dt is None:
            dt = datetime.now(timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        _, addr = parseaddr(msg.get("From", "") or "")
        if not (addr and "@" in addr):
            addr = "-"
        wday = _WDAYS[dt.weekday()]
        month = _MONTHS[dt.month - 1]
        timestr = f"{wday} {month} {dt.day:2d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} {dt.year}"
        handle.write(f"From {addr} {timestr}\n".encode("ascii", errors="replace"))
        handle.write(escape_mboxrd(article))
        if not article.endswith(b"\n"):
            handle.write(b"\n")
        handle.write(b"\n")


def split_articles(data: bytes) -> List[bytes]:
    parts = ARTICLE_SPLIT_RE.split(data)
    if len(parts) > 1:
        return [part for part in parts if part.strip()]
    return [data]


def find_gz_files(root: Path) -> List[Path]:
    return sorted(path for path in root.rglob("*.gz") if path.is_file())


def decompress_gz(path: Path) -> Optional[bytes]:
    try:
        with gzip.open(path, "rb") as handle:
            return handle.read()
    except (OSError, gzip.BadGzipFile) as exc:
        print(f"Warning: skipping {path}: {exc}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decompress .gz Usenet archives into a single mbox file."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Root directory to search for .gz files (default: current directory)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="archive.mbox",
        help="Output mbox path (default: archive.mbox in current directory)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print every file processed",
    )
    args = parser.parse_args()

    search_root = Path(args.directory).resolve()
    if not search_root.is_dir():
        print(f"Error: {search_root} is not a directory", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    gz_files = find_gz_files(search_root)
    if not gz_files:
        print(f"Error: no .gz files found under {search_root}", file=sys.stderr)
        return 1

    files_processed = 0
    files_failed = 0
    articles_written = 0

    with output_path.open("wb") as mbox_handle:
        for gz_path in gz_files:
            data = decompress_gz(gz_path)
            if data is None:
                files_failed += 1
                continue

            chunks = split_articles(data)
            for chunk in chunks:
                write_mbox_message(mbox_handle, chunk)
                articles_written += 1

            files_processed += 1
            if args.verbose:
                rel_path = gz_path.relative_to(search_root)
                print(
                    f"Processing: {rel_path} ({len(chunks)} articles)",
                    file=sys.stderr,
                )

    if articles_written == 0:
        print("Error: no articles written", file=sys.stderr)
        return 1

    output_size = output_path.stat().st_size if output_path.exists() else 0
    print(
        f"Done: {files_processed} .gz files processed, "
        f"{articles_written} articles written to {output_path} "
        f"({output_size} bytes)",
        file=sys.stderr,
    )
    if files_failed:
        print(f"Warning: {files_failed} .gz files skipped due to errors", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
