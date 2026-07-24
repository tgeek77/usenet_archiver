#!/usr/bin/env python3
"""Usenet Archiver CLI — fetch NNTP articles into mbox (sinntp-parity features)."""

from __future__ import annotations

import argparse
import email
import logging
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from email.generator import BytesGenerator
from io import BytesIO
from typing import Callable, List, Optional, Tuple

from .creds import resolve_credentials
from .fetch import fetch_articles_parallel
from .mboxout import MboxWriter
from .nntp import NNTPClient, NNTPError
from .overview import find_articles_in_date_range
from .plugins import apply_plugins, parse_plugin_spec

# Global so SIGTERM can close an open writer / stop workers.
_ACTIVE_WRITER: Optional[MboxWriter] = None
_STOP_EVENT: Optional[threading.Event] = None
_TERMINATED = False


class TerminatedBySignal(Exception):
    """Raised when SIGTERM is received during a pull."""


def _handle_sigterm(signum, frame):
    global _TERMINATED
    _TERMINATED = True
    if _STOP_EVENT is not None:
        _STOP_EVENT.set()
    if _ACTIVE_WRITER is not None:
        try:
            _ACTIVE_WRITER.close()
        except Exception:
            pass
    raise TerminatedBySignal("terminated by signal")


def parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError("Date must be in YYYY-MM-DD format") from e


def parse_group_spec(spec: str) -> Tuple[str, Optional[str]]:
    """Parse ``group`` or ``group>filename``."""
    if ">" in spec:
        group, filename = spec.split(">", 1)
        return group.strip(), filename.strip() or None
    return spec.strip(), None


def collect_group_specs(newsgroups: Optional[List[str]], groups_file: Optional[str]) -> List[Tuple[str, Optional[str]]]:
    specs: List[Tuple[str, Optional[str]]] = []
    for item in newsgroups or []:
        g, f = parse_group_spec(item)
        if g:
            specs.append((g, f))
    if groups_file:
        with open(groups_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                g, f = parse_group_spec(line)
                if g:
                    specs.append((g, f))
    return specs


def normalize_date_range(start_date, end_date, verbose: bool = False, today=None):
    """Fill missing bounds: lone start → end=today UTC; lone end → start=1990-01-01.

    An open-ended ``start`` with no ``end`` resolves ``end`` to *today* (UTC).
    Running the same "since DATE" job on a later calendar day therefore yields a
    different window and a different mbox name.

    ``today`` may be a ``date`` or ``datetime`` (for tests). Returns
    ``(start_date, end_date)``. Raises ``ValueError`` if start > end.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()
    elif hasattr(today, "date") and callable(today.date):
        today = today.date()

    if start_date is not None and end_date is None:
        end_date = datetime.combine(today, datetime.min.time())
        if verbose:
            print(f"Note: --end-date omitted; using end date {end_date.date()} (UTC).")
    elif end_date is not None and start_date is None:
        start_date = datetime(1990, 1, 1)
        if verbose:
            print(f"Note: --start-date omitted; using start date {start_date.date()}.")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start date must be on or before end date")
    return start_date, end_date


def mbox_name_for(group: str, filename: Optional[str], start_date, end_date) -> str:
    """Build the output mbox path. Date-window jobs get distinct dated names.

    Example: start=2025-07-01 with no end on July 10 →
    ``group-20250701-20250710.mbox``; the same request on July 11 →
    ``group-20250701-20250711.mbox`` (a separate pull).
    """
    if filename:
        return filename
    if start_date is not None and end_date is not None:
        return f"{group}-{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.mbox"
    return f"{group}.mbox"


def setup_logging(verbose: bool, syslog: bool, log_filename: Optional[str] = None) -> logging.Logger:
    root = logging.getLogger()
    root.handlers.clear()
    level = logging.DEBUG if verbose else logging.INFO
    root.setLevel(level)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    if syslog:
        try:
            from logging.handlers import SysLogHandler

            handler = SysLogHandler(facility=SysLogHandler.LOG_NEWS)
            handler.setFormatter(logging.Formatter("usenet_archiver: %(message)s"))
            root.addHandler(handler)
        except Exception as e:
            sys.stderr.write(f"Warning: syslog unavailable ({e}), using stderr\n")

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    if log_filename:
        fh = logging.FileHandler(log_filename)
        fh.setFormatter(formatter)
        root.addHandler(fh)

    return logging.getLogger("usenet_archiver")


def normalize_message_id(mid: str) -> str:
    mid = mid.strip()
    if "@" not in mid:
        raise ValueError("Message-ID must contain '@'")
    if not mid.startswith("<"):
        mid = f"<{mid}>"
    return mid


def message_to_bytes(msg) -> bytes:
    buf = BytesIO()
    BytesGenerator(buf, mangle_from_=False).flatten(msg)
    return buf.getvalue()


def mark_completed(completed_log: str, mbox_filename: str, logger: logging.Logger) -> None:
    """Append ``mbox_filename`` to the completed-jobs log after a successful pull."""
    try:
        with open(completed_log, "a", encoding="utf-8") as fh:
            fh.write(f"{mbox_filename}\n")
        logger.info("Recorded successful pull of %s in %s", mbox_filename, completed_log)
    except OSError as e:
        logger.error("Failed to update %s: %s", completed_log, e)


def pull_group(
    client: NNTPClient,
    group: str,
    mbox_filename: str,
    start_date,
    end_date,
    overview_chunk: int,
    dedup: bool,
    plugins: list,
    completed_log: str,
    logger: logging.Logger,
    conn_kwargs: dict,
    connections: int = 8,
    pipeline_depth: int = 32,
    skip_completed: bool = False,
) -> None:
    global _ACTIVE_WRITER

    # Optional short-circuit: skip an exact job name already in the completed log.
    # This is off by default because Message-ID dedup + append make re-pulls
    # incremental (a re-run only fetches articles not already in the mbox), which
    # is exactly what "catch up on new posts" needs. Enable to hard-skip finished
    # dated windows.
    if skip_completed:
        try:
            if os.path.exists(completed_log):
                with open(completed_log, encoding="utf-8") as fh:
                    done = {line.strip() for line in fh if line.strip()}
                if mbox_filename in done and os.path.exists(mbox_filename):
                    logger.info(
                        "Skipping %s (already in %s; disable skip-completed to catch up)",
                        mbox_filename,
                        completed_log,
                    )
                    return
                if mbox_filename in done and not os.path.exists(mbox_filename):
                    logger.info(
                        "%s is listed in %s but the mbox is missing; pulling again",
                        mbox_filename,
                        completed_log,
                    )
        except OSError as e:
            logger.warning("Could not read %s: %s", completed_log, e)

    first, last, group_resp = client.group(group)
    logger.info("GROUP %s: %s (first=%s last=%s)", group, group_resp, first, last)
    if first == 0 and last == 0:
        logger.info("Group %s is empty", group)
        mark_completed(completed_log, mbox_filename, logger)
        return

    rows = find_articles_in_date_range(
        client,
        first,
        last,
        start_date,
        end_date,
        chunk_size=overview_chunk,
    )
    logger.info("Overview matched %s articles for %s", len(rows), group)

    writer = MboxWriter(mbox_filename, dedup=dedup, flush_every=100)
    _ACTIVE_WRITER = writer
    articles_saved = 0
    articles_skipped = 0
    articles_missing = 0
    articles_errors = 0
    try:
        writer.open()
        if dedup:
            rows = [r for r in rows if not writer.has_message_id(r.message_id)]
            logger.info("After dedup filter: %s articles to fetch", len(rows))

        if not rows:
            logger.info("Nothing to fetch for %s", group)
            mark_completed(completed_log, mbox_filename, logger)
            return

        def on_article(row, content, resp):
            nonlocal articles_saved, articles_skipped, articles_missing, articles_errors
            if _TERMINATED:
                return
            if not content:
                if isinstance(resp, str) and resp.startswith("error:"):
                    articles_errors += 1
                    logger.debug("Article %s error: %s", row.article_id, resp)
                else:
                    articles_missing += 1
                    logger.debug("Article %s missing: %s", row.article_id, resp)
                return
            body = content
            if plugins:
                msg = email.message_from_bytes(content)
                msg = apply_plugins(msg, plugins)
                if msg is None:
                    articles_skipped += 1
                    return
                body = message_to_bytes(msg)
            if writer.write(body, dt=row.date, message_id=row.message_id or None):
                articles_saved += 1
            else:
                articles_skipped += 1

        stop = _STOP_EVENT if _STOP_EVENT is not None else threading.Event()
        rows_to_fetch = len(rows)
        _fetched_ok, _missing, _errors, elapsed = fetch_articles_parallel(
            rows=rows,
            group=group,
            conn_kwargs=conn_kwargs,
            connections=connections,
            pipeline_depth=pipeline_depth,
            on_article=on_article,
            stop_event=stop,
        )
        del _fetched_ok, _missing, _errors  # on_article counters are authoritative
        attempted = articles_saved + articles_skipped + articles_missing + articles_errors
        arts_per_s = attempted / max(elapsed, 1e-6)
        kib_per_s = (writer.bytes_written / 1024.0) / max(elapsed, 1e-6)
        logger.info(
            "Group %s done: saved=%s skipped=%s missing=%s errors=%s "
            "(%.1fs, %.1f art/s, %.1f KiB/s, connections=%s pipeline=%s)",
            group,
            articles_saved,
            articles_skipped,
            articles_missing,
            articles_errors,
            elapsed,
            arts_per_s,
            kib_per_s,
            connections,
            pipeline_depth,
        )
        # Only record completion after a clean, finished pull. Cancelled /
        # interrupted runs and hard fetch errors must not poison the log —
        # otherwise skip-completed (and earlier default skip) treats a failed
        # first attempt as done forever.
        if _TERMINATED or stop.is_set():
            logger.warning(
                "Pull of %s was cancelled/interrupted; not adding to %s",
                mbox_filename,
                completed_log,
            )
            raise TerminatedBySignal("terminated")
        if articles_errors > 0 or attempted < rows_to_fetch:
            logger.warning(
                "Pull of %s did not finish cleanly "
                "(errors=%s attempted=%s/%s); not adding to %s",
                mbox_filename,
                articles_errors,
                attempted,
                rows_to_fetch,
                completed_log,
            )
            return
        mark_completed(completed_log, mbox_filename, logger)
    finally:
        writer.close()
        _ACTIVE_WRITER = None


def cmd_list_groups(client: NNTPClient, wildmat: Optional[str]) -> int:
    names = client.list_active(wildmat)
    for name in names:
        sys.stdout.buffer.write(name.encode("utf-8", errors="surrogateescape") + b"\n")
    return 0


def cmd_get_message(client: NNTPClient, message_id: str) -> int:
    mid = normalize_message_id(message_id)
    content, resp = client.article(mid)
    if not content:
        sys.stderr.write(f"Article not found: {resp}\n")
        return 4
    sys.stdout.buffer.write(content)
    if not content.endswith(b"\n"):
        sys.stdout.buffer.write(b"\n")
    return 0


def cmd_post(client: NNTPClient, newsgroups: List[str], plugins: list) -> int:
    raw = sys.stdin.buffer.read()
    if not raw.strip():
        sys.stderr.write("No message on stdin\n")
        return 4
    msg = email.message_from_bytes(raw)
    if "Newsgroups" not in msg and newsgroups:
        msg["Newsgroups"] = ",".join(newsgroups)
    if plugins:
        msg = apply_plugins(msg, plugins)
        if msg is None:
            sys.stderr.write("Message dropped by plugin\n")
            return 4
    payload = message_to_bytes(msg)
    resp = client.post(payload)
    sys.stderr.write(f"{resp}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch NNTP articles and save to mbox")
    parser.add_argument("--server", help="NNTP server (host or host:port); default $NNTPSERVER or /etc/news/server")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="NNTP server port (default: 563 with TLS, 119 for plain NNTP)",
    )
    parser.add_argument("--username", help="Username for authentication")
    parser.add_argument("--password", help="Password for authentication (prefer --password-file or $NNTP_PASSWORD)")
    parser.add_argument("--password-file", help="Read password from file")
    parser.add_argument("--no-netrc", dest="netrc", action="store_false", help="Ignore credentials in ~/.netrc")
    parser.set_defaults(netrc=True)

    parser.add_argument(
        "--newsgroup",
        action="append",
        dest="newsgroups",
        metavar="GROUP[>FILE]",
        help="Newsgroup to fetch (repeatable; optional group>filename)",
    )
    parser.add_argument("--groups-file", help="File with one group[>filename] per line")

    parser.add_argument(
        "--no-ssl",
        dest="use_ssl",
        action="store_false",
        help="Disable TLS and use plain NNTP (typical port 119)",
    )
    parser.set_defaults(use_ssl=True)
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--syslog", action="store_true", help="Also log to syslog (LOG_NEWS)")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout for operations (seconds)")
    parser.add_argument(
        "--start-date",
        help="Start date (YYYY-MM-DD). May be used alone; end defaults to today (UTC).",
    )
    parser.add_argument(
        "--end-date",
        help="End date (YYYY-MM-DD). May be used alone; start defaults to 1990-01-01.",
    )
    parser.add_argument(
        "--overview-chunk",
        type=int,
        default=10000,
        help="OVER/XOVER chunk size for date scanning (default 10000)",
    )
    parser.add_argument("--no-dedup", dest="dedup", action="store_false", help="Disable Message-ID deduplication")
    parser.set_defaults(dedup=True)
    parser.add_argument(
        "--skip-completed",
        action="store_true",
        help="Skip a group whose exact mbox job is already in completed_newsgroups.log "
        "(off by default; re-pulls are incremental via Message-ID dedup)",
    )
    parser.add_argument(
        "--plugin",
        action="append",
        default=[],
        metavar="PLUGIN",
        help="Apply plugin (name or name:arg:key=value); repeatable",
    )
    parser.add_argument(
        "--connections",
        type=int,
        default=8,
        metavar="N",
        help="Parallel NNTP connections for ARTICLE fetch (default 8; max depends on provider)",
    )
    parser.add_argument(
        "--pipeline-depth",
        type=int,
        default=32,
        metavar="N",
        help="ARTICLE commands to pipeline per connection before reading (default 32)",
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--list-groups",
        nargs="?",
        const="",
        default=None,
        metavar="WILDMAT",
        help="List available groups (optional wildmat) and exit",
    )
    mode.add_argument("--message-id", metavar="ID", help="Fetch one article by Message-ID to stdout")
    mode.add_argument("--post", action="store_true", help="Post one RFC 5322 message from stdin")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    global _STOP_EVENT

    parser = build_parser()
    args = parser.parse_args(argv)

    _STOP_EVENT = threading.Event()
    signal.signal(signal.SIGTERM, _handle_sigterm)

    if args.connections < 1:
        parser.error("--connections must be >= 1")
    if args.pipeline_depth < 1:
        parser.error("--pipeline-depth must be >= 1")
    if args.connections > 99:
        # Soft warning only — some providers allow 99+.
        sys.stderr.write(
            f"Warning: --connections {args.connections} is high; "
            "check your provider's concurrent-connection limit.\n"
        )

    try:
        endpoint = resolve_credentials(
            server=args.server,
            port=args.port,
            username=args.username,
            password=args.password,
            password_file=args.password_file,
            use_netrc=args.netrc,
            use_ssl=args.use_ssl,
        )
    except SystemExit as e:
        if e.code == 2:
            sys.stderr.write(
                "No NNTP server specified. Use --server, set $NNTPSERVER, or create /etc/news/server.\n"
            )
            return 2
        raise
    except FileNotFoundError as e:
        sys.stderr.write(f"Password file error: {e}\n")
        return 2
    except OSError as e:
        sys.stderr.write(f"Connection/config error: {e}\n")
        return 3

    start_date = parse_date(args.start_date) if args.start_date else None
    end_date = parse_date(args.end_date) if args.end_date else None
    try:
        start_date, end_date = normalize_date_range(start_date, end_date, verbose=args.verbose)
    except ValueError as e:
        parser.error(str(e).replace("start date", "--start-date").replace("end date", "--end-date"))

    plugins: List[Callable] = []
    for spec in args.plugin:
        try:
            plugins.append(parse_plugin_spec(spec))
        except ValueError as e:
            parser.error(str(e))

    is_pull = args.list_groups is None and args.message_id is None and not args.post
    group_specs = collect_group_specs(args.newsgroups, args.groups_file)
    if is_pull and not group_specs:
        parser.error("pull mode requires --newsgroup and/or --groups-file")

    logger = setup_logging(args.verbose, args.syslog)

    client = NNTPClient(
        server=endpoint.host,
        port=endpoint.port,
        username=endpoint.username,
        password=endpoint.password,
        use_ssl=args.use_ssl,
        verbose=args.verbose,
        timeout=args.timeout,
    )

    try:
        client.connect()
    except (NNTPError, OSError) as e:
        sys.stderr.write(f"Connection failed: {e}\n")
        return 3

    try:
        if args.list_groups is not None:
            wildmat = args.list_groups or None
            return cmd_list_groups(client, wildmat)

        if args.message_id is not None:
            try:
                return cmd_get_message(client, args.message_id)
            except ValueError as e:
                sys.stderr.write(f"{e}\n")
                return 4

        if args.post:
            groups = [g for g, _ in group_specs]
            return cmd_post(client, groups, plugins)

        # Default: pull
        completed_log = "completed_newsgroups.log"
        for group, filename in group_specs:
            mbox_filename = mbox_name_for(group, filename, start_date, end_date)
            log_filename = mbox_filename.rsplit(".", 1)[0] + ".log"
            # Per-group file log
            file_handler = logging.FileHandler(log_filename)
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logging.getLogger().addHandler(file_handler)
            conn_kwargs = {
                "server": endpoint.host,
                "port": endpoint.port,
                "username": endpoint.username,
                "password": endpoint.password,
                "use_ssl": args.use_ssl,
                "verbose": args.verbose,
                "timeout": args.timeout,
            }
            try:
                pull_group(
                    client=client,
                    group=group,
                    mbox_filename=mbox_filename,
                    start_date=start_date,
                    end_date=end_date,
                    overview_chunk=args.overview_chunk,
                    dedup=args.dedup,
                    plugins=plugins,
                    completed_log=completed_log,
                    logger=logger,
                    conn_kwargs=conn_kwargs,
                    connections=args.connections,
                    pipeline_depth=args.pipeline_depth,
                    skip_completed=args.skip_completed,
                )
            except TerminatedBySignal:
                logger.warning("Terminated while processing %s", group)
                return 4
            except Exception as e:
                logger.error("Failed group %s: %s", group, e)
                # Continue with remaining groups
            finally:
                logging.getLogger().removeHandler(file_handler)
                file_handler.close()
        return 0
    except TerminatedBySignal:
        return 4
    except NNTPError as e:
        sys.stderr.write(f"NNTP error: {e}\n")
        return 4
    finally:
        try:
            client.quit()
        except Exception:
            client.close()


def run() -> None:
    """Zipapp / console_scripts entry point (honors exit codes)."""
    raise SystemExit(main())


if __name__ == "__main__":
    run()
