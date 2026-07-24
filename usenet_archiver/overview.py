#!/usr/bin/env python3
"""Overview-based date range discovery for NNTP groups.

Uses OVER / XOVER (with XHDR DATE fallback), bisects on Date to bracket a
window, then bulk-scans overview chunks to produce an exact article ID list.
Provider-specific heuristics (hardcoded retention years, min IDs) are not used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


@dataclass
class OverviewRow:
    article_id: int
    subject: str = ""
    from_: str = ""
    date: Optional[datetime] = None
    message_id: str = ""
    references: str = ""
    bytes_: int = 0
    lines: int = 0
    xref: str = ""


def parse_overview_line(raw: bytes) -> Optional[OverviewRow]:
    """Parse one OVER/XOVER tab-separated line into an OverviewRow."""
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        try:
            text = raw.decode("latin-1", errors="replace")
        except Exception:
            return None
    # Fields: artnum\tSubject\tFrom\tDate\tMessage-ID\tReferences\tbytes\tlines[\tXref]
    parts = text.split("\t")
    if not parts or not parts[0].strip().isdigit():
        return None
    article_id = int(parts[0].strip())

    def field(i: int) -> str:
        return parts[i].strip() if i < len(parts) else ""

    date = None
    date_str = field(3)
    if date_str and date_str != "none":
        try:
            date = parsedate_to_datetime(date_str)
            if date is not None and date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            date = None

    bytes_ = 0
    lines = 0
    try:
        if field(6):
            bytes_ = int(field(6))
    except ValueError:
        pass
    try:
        if field(7):
            lines = int(field(7))
    except ValueError:
        pass

    return OverviewRow(
        article_id=article_id,
        subject=field(1),
        from_=field(2),
        date=date,
        message_id=field(4),
        references=field(5),
        bytes_=bytes_,
        lines=lines,
        xref=field(8),
    )


def parse_xhdr_date_pair(article_id: int, date_str: str) -> OverviewRow:
    date = None
    if date_str and date_str.lower() != "none":
        try:
            date = parsedate_to_datetime(date_str)
            if date is not None and date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            date = None
    return OverviewRow(article_id=article_id, date=date)


def _date_only(dt: Optional[datetime]):
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


FetchOverview = Callable[[int, int], List[OverviewRow]]


def fetch_overview_chunk(client, start_id: int, end_id: int) -> List[OverviewRow]:
    """Fetch overview rows for [start_id, end_id] via OVER/XOVER or XHDR DATE."""
    lines, cmd, resp = client.over(start_id, end_id)
    if cmd and resp.startswith("224"):
        rows = []
        for raw in lines:
            row = parse_overview_line(raw)
            if row is not None:
                rows.append(row)
        return rows

    # Fallback: XHDR DATE
    pairs = client.xhdr_date(start_id, end_id)
    return [parse_xhdr_date_pair(aid, dstr) for aid, dstr in pairs]


def sample_date_at(fetch: FetchOverview, article_id: int, first: int, last: int) -> Optional[datetime]:
    """Return the Date of the nearest available article at or near article_id."""
    lo = max(first, article_id - 5)
    hi = min(last, article_id + 5)
    rows = fetch(lo, hi)
    # Prefer exact match, else closest with a date
    exact = [r for r in rows if r.article_id == article_id and r.date is not None]
    if exact:
        return exact[0].date
    dated = [r for r in rows if r.date is not None]
    if not dated:
        return None
    dated.sort(key=lambda r: abs(r.article_id - article_id))
    return dated[0].date


def bisect_lower(fetch: FetchOverview, first: int, last: int, start_date) -> int:
    """Smallest article_id whose Date is >= start_date (approx; dates not strictly monotonic)."""
    lo, hi = first, last
    while lo < hi:
        mid = (lo + hi) // 2
        dt = sample_date_at(fetch, mid, first, last)
        if dt is None:
            # Skip gaps: move mid right a bit
            lo = mid + 1
            continue
        if _date_only(dt) is None or _date_only(dt) < start_date:
            lo = mid + 1
        else:
            hi = mid
    return lo


def bisect_upper(fetch: FetchOverview, first: int, last: int, end_date) -> int:
    """Largest article_id whose Date is <= end_date (approx)."""
    lo, hi = first, last
    while lo < hi:
        mid = (lo + hi + 1) // 2
        dt = sample_date_at(fetch, mid, first, last)
        if dt is None:
            hi = mid - 1
            continue
        if _date_only(dt) is None or _date_only(dt) > end_date:
            hi = mid - 1
        else:
            lo = mid
    return lo


def find_articles_in_date_range(
    client,
    first: int,
    last: int,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    chunk_size: int = 10000,
    margin: int = 500,
) -> List[OverviewRow]:
    """Return overview rows whose Date falls in [start_date, end_date] inclusive.

    If both dates are None, returns overview for the entire group (chunked).
    """
    if first > last:
        return []

    def fetch(a: int, b: int) -> List[OverviewRow]:
        return fetch_overview_chunk(client, a, b)

    if start_date is None and end_date is None:
        return list(_scan_chunks(fetch, first, last, chunk_size, None, None))

    start_d = start_date.date() if start_date else None
    end_d = end_date.date() if end_date else None

    # Bracket with bisect when we have bounds
    range_first, range_last = first, last
    if start_d is not None:
        try:
            range_first = bisect_lower(fetch, first, last, start_d)
        except Exception as e:
            logger.warning("bisect_lower failed: %s; scanning full range", e)
            range_first = first
    if end_d is not None:
        try:
            range_last = bisect_upper(fetch, first, last, end_d)
        except Exception as e:
            logger.warning("bisect_upper failed: %s; scanning full range", e)
            range_last = last

    # Widen for non-monotonic dates
    range_first = max(first, range_first - margin)
    range_last = min(last, range_last + margin)
    if range_first > range_last:
        logger.info("Empty bracket after bisect (%s > %s)", range_first, range_last)
        return []

    logger.info(
        "Overview scan window: %s-%s (group %s-%s, chunk=%s)",
        range_first,
        range_last,
        first,
        last,
        chunk_size,
    )
    return list(_scan_chunks(fetch, range_first, range_last, chunk_size, start_d, end_d))


def _scan_chunks(
    fetch: FetchOverview,
    start_id: int,
    end_id: int,
    chunk_size: int,
    start_d,
    end_d,
) -> List[OverviewRow]:
    matched: List[OverviewRow] = []
    cursor = start_id
    while cursor <= end_id:
        chunk_end = min(end_id, cursor + chunk_size - 1)
        try:
            rows = fetch(cursor, chunk_end)
        except Exception as e:
            logger.warning("Overview chunk %s-%s failed: %s", cursor, chunk_end, e)
            cursor = chunk_end + 1
            continue
        for row in rows:
            if start_d is None and end_d is None:
                matched.append(row)
                continue
            if row.date is None:
                # Include undated articles when filtering? Plan says filter on overview Date.
                # Keep them so rare missing Date headers are not silently dropped from archive.
                matched.append(row)
                continue
            d = _date_only(row.date)
            if d is None:
                matched.append(row)
                continue
            if start_d is not None and d < start_d:
                continue
            if end_d is not None and d > end_d:
                continue
            matched.append(row)
        cursor = chunk_end + 1
    matched.sort(key=lambda r: r.article_id)
    return matched


def filter_rows_by_dedup(rows: Sequence[OverviewRow], seen_ids: set) -> List[OverviewRow]:
    """Drop rows whose Message-ID is already in seen_ids."""
    out = []
    for row in rows:
        mid = (row.message_id or "").strip()
        if mid and mid in seen_ids:
            continue
        out.append(row)
    return out
