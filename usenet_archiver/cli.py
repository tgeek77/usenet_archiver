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


def filter_binary_groups(
    specs: List[Tuple[str, Optional[str]]], logger: Optional[logging.Logger] = None
) -> List[Tuple[str, Optional[str]]]:
    """Remove binary-looking groups; log each skip."""
    from .policy import filter_group_specs

    kept, skipped = filter_group_specs(specs)
    if skipped and logger is not None:
        for name in skipped:
            logger.info("Skipping binary newsgroup %s", name)
    elif skipped:
        for name in skipped:
            sys.stderr.write(f"Skipping binary newsgroup {name}\n")
    return kept


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
    dry_run: bool = False,
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
        if dry_run:
            logger.info("DRY-RUN: group %s is empty (would write %s)", group, mbox_filename)
            return
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
    overview_count = len(rows)
    logger.info("Overview matched %s articles for %s", overview_count, group)

    # Index existing mbox for dedup without opening for append (dry-run must not
    # create or modify the mbox / completed log).
    writer = MboxWriter(mbox_filename, dedup=dedup, flush_every=100)
    if dedup:
        rows = [r for r in rows if not writer.has_message_id(r.message_id)]
        logger.info("After dedup filter: %s articles to fetch", len(rows))

    if dry_run:
        date_note = ""
        dated = [r.date for r in rows if getattr(r, "date", None) is not None]
        if dated:
            date_note = f", article dates {min(dated).date()} .. {max(dated).date()}"
        plugin_note = f", plugins={len(plugins)}" if plugins else ""
        logger.info(
            "DRY-RUN: would fetch %s article(s) for %s → %s "
            "(overview=%s, already_in_mbox=%s%s%s; no ARTICLE / mbox write)",
            len(rows),
            group,
            mbox_filename,
            overview_count,
            overview_count - len(rows),
            date_note,
            plugin_note,
        )
        return

    if not rows:
        logger.info("Nothing to fetch for %s", group)
        mark_completed(completed_log, mbox_filename, logger)
        return

    _ACTIVE_WRITER = writer
    articles_saved = 0
    articles_skipped = 0
    articles_missing = 0
    articles_errors = 0
    try:
        writer.open()

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


def _connection_parser() -> argparse.ArgumentParser:
    """Shared NNTP connection / logging options for all subcommands."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument(
        "-s",
        "--server",
        help="NNTP server (host or host:port); default $NNTPSERVER or /etc/news/server",
    )
    p.add_argument(
        "-P",
        "--port",
        type=int,
        default=None,
        help="NNTP server port (default: 563 with TLS, 119 for plain NNTP)",
    )
    p.add_argument(
        "-u",
        "--user",
        "--username",
        dest="username",
        help="Username for authentication",
    )
    p.add_argument(
        "--password",
        help="Password for authentication (prefer --password-file or $NNTP_PASSWORD)",
    )
    p.add_argument(
        "--password-file",
        "--pass-file",
        dest="password_file",
        help="Path to a text file whose entire contents are the NNTP password "
        "(trailing newline optional). Prefer this over --password.",
    )
    p.add_argument(
        "--no-netrc",
        dest="netrc",
        action="store_false",
        help="Ignore credentials in ~/.netrc",
    )
    p.set_defaults(netrc=True)
    p.add_argument(
        "--no-ssl",
        dest="use_ssl",
        action="store_false",
        help="Disable TLS and use plain NNTP (typical port 119)",
    )
    p.set_defaults(use_ssl=True)
    p.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    p.add_argument("--syslog", action="store_true", help="Also log to syslog (LOG_NEWS)")
    p.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=60,
        help="Timeout for operations (seconds)",
    )
    return p


def build_parser() -> argparse.ArgumentParser:
    from . import __version__

    conn = _connection_parser()
    parser = argparse.ArgumentParser(
        prog="usenet-archiver -c",
        description="NNTP text archiver CLI (use subcommands). GUI is the default without -c.",
        epilog=(
            "Examples:\n"
            "  usenet-archiver -c pull -s news.example.com -u alice -g news.groups -n\n"
            "  usenet-archiver -c list-groups 'comp.*'\n"
            "  usenet-archiver -c get '<mid@example.com>'\n"
            "  usenet-archiver -c post -g misc.test < msg.eml\n"
            "\n"
            "Without -c, usenet-archiver launches the GUI. "
            "Top-level --help / --version work without -c.\n"
            "Short and long forms are interchangeable (e.g. -s/--server, -u/--user)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"usenet-archiver {__version__}",
    )

    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # --- pull ------------------------------------------------------------
    pull = sub.add_parser(
        "pull",
        parents=[conn],
        help="Fetch articles into mbox (overview + ARTICLE)",
        description="Fetch newsgroup articles into mbox archives.",
    )
    pull.add_argument(
        "-g",
        "--group",
        "--newsgroup",
        action="append",
        dest="newsgroups",
        metavar="GROUP[>FILE]",
        help="Newsgroup to fetch (repeatable; optional group>filename)",
    )
    pull.add_argument(
        "-f",
        "--file",
        "--groups-file",
        dest="groups_file",
        help="File with one group[>filename] per line",
    )
    pull.add_argument(
        "--start",
        "--start-date",
        dest="start_date",
        help="Start date (YYYY-MM-DD). May be used alone; end defaults to today (UTC).",
    )
    pull.add_argument(
        "--end",
        "--end-date",
        dest="end_date",
        help="End date (YYYY-MM-DD). May be used alone; start defaults to 1990-01-01.",
    )
    pull.add_argument(
        "--overview-chunk",
        type=int,
        default=10000,
        help="OVER/XOVER chunk size for date scanning (default 10000)",
    )
    pull.add_argument(
        "--no-dedup",
        dest="dedup",
        action="store_false",
        help="Disable Message-ID deduplication",
    )
    pull.set_defaults(dedup=True)
    pull.add_argument(
        "--skip-completed",
        action="store_true",
        help="Skip a group whose exact mbox job is already in completed_newsgroups.log",
    )
    pull.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Plan only: overview + dedup; no ARTICLE download or mbox write",
    )
    pull.add_argument(
        "--plugin",
        action="append",
        default=[],
        metavar="PLUGIN",
        help="Apply plugin (name or name:arg:key=value); repeatable",
    )
    pull.add_argument(
        "-C",
        "--connections",
        type=int,
        default=8,
        metavar="N",
        help="Parallel NNTP connections for ARTICLE fetch (default 8)",
    )
    pull.add_argument(
        "-D",
        "--depth",
        "--pipeline-depth",
        dest="pipeline_depth",
        type=int,
        default=32,
        metavar="N",
        help="ARTICLE commands to pipeline per connection (default 32)",
    )

    # --- list-groups -----------------------------------------------------
    lg = sub.add_parser(
        "list-groups",
        parents=[conn],
        help="List available newsgroups",
        description="List newsgroups from the server (optional wildmat).",
    )
    lg.add_argument(
        "wildmat",
        nargs="?",
        default=None,
        help="Optional wildmat pattern (e.g. 'comp.lang.*')",
    )

    # --- get -------------------------------------------------------------
    getp = sub.add_parser(
        "get",
        parents=[conn],
        help="Fetch one article by Message-ID to stdout",
        description="Fetch a single article by Message-ID and write it to stdout.",
    )
    getp.add_argument(
        "message_id",
        help="Message-ID (with or without surrounding <angle brackets>)",
    )

    # --- post ------------------------------------------------------------
    post = sub.add_parser(
        "post",
        parents=[conn],
        help="Post one RFC 5322 message from stdin",
        description="Read one message from stdin and POST it.",
    )
    post.add_argument(
        "-g",
        "--group",
        "--newsgroup",
        action="append",
        dest="newsgroups",
        metavar="GROUP",
        help="Newsgroup(s) if the message has no Newsgroups header",
    )
    post.add_argument(
        "--plugin",
        action="append",
        default=[],
        metavar="PLUGIN",
        help="Apply plugin (name or name:arg:key=value); repeatable",
    )

    return parser


def _resolve_endpoint(args):
    return resolve_credentials(
        server=args.server,
        port=args.port,
        username=args.username,
        password=args.password,
        password_file=args.password_file,
        use_netrc=args.netrc,
        use_ssl=args.use_ssl,
    )


def _connect_client(args, endpoint) -> NNTPClient:
    client = NNTPClient(
        server=endpoint.host,
        port=endpoint.port,
        username=endpoint.username,
        password=endpoint.password,
        use_ssl=args.use_ssl,
        verbose=args.verbose,
        timeout=args.timeout,
    )
    client.connect()
    return client


def _parse_plugins(specs: List[str], parser: argparse.ArgumentParser) -> list:
    plugins: List[Callable] = []
    for spec in specs or []:
        try:
            plugins.append(parse_plugin_spec(spec))
        except ValueError as e:
            parser.error(str(e))
    return plugins


def main(argv: Optional[List[str]] = None) -> int:
    global _STOP_EVENT

    parser = build_parser()
    args = parser.parse_args(argv)

    _STOP_EVENT = threading.Event()
    signal.signal(signal.SIGTERM, _handle_sigterm)

    try:
        endpoint = _resolve_endpoint(args)
    except SystemExit as e:
        if e.code == 2:
            sys.stderr.write(
                "No NNTP server specified. Use --server / -s, set $NNTPSERVER, "
                "or create /etc/news/server.\n"
            )
            return 2
        raise
    except ValueError as e:
        sys.stderr.write(f"{e}\n")
        return 2
    except FileNotFoundError as e:
        sys.stderr.write(f"Password file error: {e}\n")
        return 2
    except OSError as e:
        sys.stderr.write(f"Connection/config error: {e}\n")
        return 3

    logger = setup_logging(args.verbose, args.syslog)

    try:
        client = _connect_client(args, endpoint)
    except (NNTPError, OSError) as e:
        sys.stderr.write(f"Connection failed: {e}\n")
        return 3

    try:
        if args.command == "list-groups":
            return cmd_list_groups(client, args.wildmat)

        if args.command == "get":
            try:
                return cmd_get_message(client, args.message_id)
            except ValueError as e:
                sys.stderr.write(f"{e}\n")
                return 4

        if args.command == "post":
            plugins = _parse_plugins(args.plugin, parser)
            group_specs = collect_group_specs(args.newsgroups, None)
            groups = [g for g, _ in group_specs]
            return cmd_post(client, groups, plugins)

        # pull
        if args.connections < 1:
            parser.error("--connections must be >= 1")
        if args.pipeline_depth < 1:
            parser.error("--pipeline-depth must be >= 1")
        if args.connections > 99:
            sys.stderr.write(
                f"Warning: --connections {args.connections} is high; "
                "check your provider's concurrent-connection limit.\n"
            )

        start_date = parse_date(args.start_date) if args.start_date else None
        end_date = parse_date(args.end_date) if args.end_date else None
        try:
            start_date, end_date = normalize_date_range(
                start_date, end_date, verbose=args.verbose
            )
        except ValueError as e:
            parser.error(
                str(e)
                .replace("start date", "--start-date")
                .replace("end date", "--end-date")
            )

        plugins = _parse_plugins(args.plugin, parser)
        group_specs = collect_group_specs(args.newsgroups, args.groups_file)
        group_specs = filter_binary_groups(group_specs, logger=logger)
        if not group_specs:
            parser.error(
                "pull requires -g/--newsgroup and/or -f/--groups-file "
                "(after skipping binary groups)"
            )

        completed_log = "completed_newsgroups.log"
        for group, filename in group_specs:
            mbox_filename = mbox_name_for(group, filename, start_date, end_date)
            log_filename = mbox_filename.rsplit(".", 1)[0] + ".log"
            file_handler = logging.FileHandler(log_filename)
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            )
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
                    dry_run=args.dry_run,
                )
            except TerminatedBySignal:
                logger.warning("Terminated while processing %s", group)
                return 4
            except Exception as e:
                logger.error("Failed group %s: %s", group, e)
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
