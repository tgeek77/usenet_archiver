#!/usr/bin/env python3
"""mboxrd writer helpers: envelope lines, From_ escaping, Message-ID dedup index."""

from __future__ import annotations

import email
import re
import threading
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import BinaryIO, Optional, Set


# English weekday / month abbreviations (locale-independent).
_WDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

_MESSAGE_ID_RE = re.compile(rb"(?im)^Message-ID:\s*(.+?)\s*$")
_FROM_RE = re.compile(rb"(?im)^From:\s*(.+?)\s*$")
_DATE_RE = re.compile(rb"(?im)^Date:\s*(.+?)\s*$")


def format_envelope_utc(dt: Optional[datetime], from_addr: str = "-") -> bytes:
    """Build a locale-independent mbox From_ separator line in UTC.

    Format: ``From addr Day Mon DD HH:MM:SS YYYY\\n``
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    wday = _WDAYS[dt.weekday()]
    month = _MONTHS[dt.month - 1]
    timestr = f"{wday} {month} {dt.day:2d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} {dt.year}"
    addr = from_addr.strip() if from_addr and from_addr.strip() else "-"
    # Avoid spaces / control chars in the envelope address token
    if " " in addr or "\t" in addr or "\n" in addr:
        addr = "-"
    return f"From {addr} {timestr}\n".encode("ascii", errors="replace")


def escape_mboxrd(data: bytes) -> bytes:
    """Escape body/header lines that would look like mbox message separators."""
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


def _header_block(article: bytes) -> bytes:
    """Return bytes up to the first blank line (header section)."""
    for sep in (b"\r\n\r\n", b"\n\n"):
        idx = article.find(sep)
        if idx >= 0:
            return article[:idx]
    return article[:4096]


def sender_from_article(article: bytes) -> str:
    """Extract a From_ envelope address from article bytes (header scan)."""
    m = _FROM_RE.search(_header_block(article))
    if not m:
        return "-"
    try:
        raw = m.group(1).decode("utf-8", errors="replace")
    except Exception:
        return "-"
    _, addr = parseaddr(raw)
    if addr and "@" in addr:
        return addr
    return "-"


def date_from_article(article: bytes) -> Optional[datetime]:
    m = _DATE_RE.search(_header_block(article))
    if not m:
        return None
    try:
        date_hdr = m.group(1).decode("ascii", errors="replace")
        return parsedate_to_datetime(date_hdr)
    except (TypeError, ValueError, OverflowError, UnicodeError):
        return None


def message_id_from_article(article: bytes) -> Optional[str]:
    m = _MESSAGE_ID_RE.search(_header_block(article))
    if not m:
        # Fallback to full parse for folded headers
        msg = email.message_from_bytes(article)
        mid = msg.get("Message-ID") or msg.get("Message-Id")
        return mid.strip() if mid else None
    try:
        return m.group(1).decode("ascii", errors="replace").strip()
    except Exception:
        return None


def write_mbox_message(handle: BinaryIO, article: bytes, dt: Optional[datetime] = None) -> None:
    """Write one article to an mboxrd file (binary handle)."""
    if dt is None:
        dt = date_from_article(article)
    addr = sender_from_article(article)
    handle.write(format_envelope_utc(dt, addr))
    handle.write(escape_mboxrd(article))
    if not article.endswith(b"\n"):
        handle.write(b"\n")
    # Blank line between messages is conventional; escape_mboxrd already ends with \n
    # so add one more blank line separator.
    handle.write(b"\n")


def index_message_ids(mbox_path: str) -> Set[str]:
    """Scan an existing mbox for Message-ID headers (byte scan, no full parse)."""
    ids: Set[str] = set()
    try:
        with open(mbox_path, "rb") as fh:
            for line in fh:
                m = _MESSAGE_ID_RE.match(line.rstrip(b"\r\n"))
                if m:
                    try:
                        ids.add(m.group(1).decode("ascii", errors="replace").strip())
                    except Exception:
                        pass
    except FileNotFoundError:
        pass
    return ids


class MboxWriter:
    """Append-mode mbox writer with optional Message-ID deduplication.

    Thread-safe. Flushes every ``flush_every`` writes (and on close) instead of
    after every article.
    """

    def __init__(self, path: str, dedup: bool = True, flush_every: int = 100):
        self.path = path
        self.dedup = dedup
        self.flush_every = max(1, flush_every)
        self._seen: Set[str] = index_message_ids(path) if dedup else set()
        self._fh: Optional[BinaryIO] = None
        self._lock = threading.Lock()
        self._since_flush = 0
        self.written = 0
        self.skipped_dup = 0
        self.bytes_written = 0

    def open(self) -> None:
        with self._lock:
            if self._fh is None:
                self._fh = open(self.path, "ab")

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.flush()
                finally:
                    self._fh.close()
                    self._fh = None
                    self._since_flush = 0

    def __enter__(self) -> "MboxWriter":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def has_message_id(self, message_id: Optional[str]) -> bool:
        if not self.dedup or not message_id:
            return False
        with self._lock:
            return message_id.strip() in self._seen

    def write(self, article: bytes, dt: Optional[datetime] = None, message_id: Optional[str] = None) -> bool:
        """Write article unless it is a duplicate. Returns True if written."""
        mid = message_id or message_id_from_article(article)
        with self._lock:
            if mid and self.dedup and mid.strip() in self._seen:
                self.skipped_dup += 1
                return False
            if self._fh is None:
                self._fh = open(self.path, "ab")
            before = self._fh.tell()
            write_mbox_message(self._fh, article, dt=dt)
            after = self._fh.tell()
            self.bytes_written += max(0, after - before)
            self._since_flush += 1
            if self._since_flush >= self.flush_every:
                self._fh.flush()
                self._since_flush = 0
            if mid:
                self._seen.add(mid.strip())
            self.written += 1
            return True
