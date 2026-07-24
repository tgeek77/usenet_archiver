#!/usr/bin/env python3
"""Parallel ARTICLE fetch: multiple NNTP connections + pipelined batches."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, List, Optional, Sequence, Tuple

from .nntp import NNTPClient, NNTPError, NNTPTimeout
from .overview import OverviewRow

logger = logging.getLogger(__name__)

# Sentinel meaning a worker has finished.
_WORKER_DONE = object()


def _chunks(items: Sequence, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _make_client(conn_kwargs: dict) -> NNTPClient:
    return NNTPClient(**conn_kwargs)


def _worker(
    worker_id: int,
    rows: Sequence[OverviewRow],
    group: str,
    conn_kwargs: dict,
    pipeline_depth: int,
    out_queue: queue.Queue,
    stop_event: threading.Event,
) -> None:
    """Fetch assigned rows; push (row, content, resp) to out_queue."""
    client: Optional[NNTPClient] = None
    emitted = 0
    try:
        client = _make_client(conn_kwargs)
        client.connect()
        client.group(group)

        for batch in _chunks(list(rows), max(1, pipeline_depth)):
            if stop_event.is_set():
                break
            ids = [r.article_id for r in batch]
            retries = 3
            while retries > 0:
                if stop_event.is_set():
                    break
                try:
                    results = client.articles_pipelined(ids)
                    for row, (_spec, content, resp) in zip(batch, results):
                        out_queue.put((row, content, resp))
                        emitted += 1
                    break
                except (NNTPTimeout, NNTPError, OSError) as e:
                    retries -= 1
                    logger.warning(
                        "worker %s pipeline failed (%s); retries left %s",
                        worker_id,
                        e,
                        retries,
                    )
                    if retries == 0:
                        for row in batch:
                            out_queue.put((row, b"", f"error: {e}"))
                            emitted += 1
                        break
                    try:
                        client.quit()
                    except Exception:
                        client.close()
                    client = _make_client(conn_kwargs)
                    client.connect()
                    client.group(group)
    except Exception as e:
        logger.error("worker %s fatal: %s", worker_id, e)
        for row in rows[emitted:]:
            out_queue.put((row, b"", f"error: {e}"))
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass
        out_queue.put(_WORKER_DONE)


def fetch_articles_parallel(
    rows: Sequence[OverviewRow],
    group: str,
    conn_kwargs: dict,
    connections: int,
    pipeline_depth: int,
    on_article: Callable[[OverviewRow, bytes, str], None],
    stop_event: Optional[threading.Event] = None,
    progress_every: int = 100,
) -> Tuple[int, int, int, float]:
    """Fetch articles using ``connections`` clients and pipelined batches.

    ``on_article(row, content, resp)`` is called from the main thread for each
    result (thread-safe writer assumed). Returns
    ``(fetched_ok, missing, errors, elapsed_seconds)``.
    """
    if not rows:
        return 0, 0, 0, 0.0

    stop_event = stop_event or threading.Event()
    n_conn = max(1, min(connections, len(rows)))
    depth = max(1, pipeline_depth)

    # Round-robin split so each worker gets a similar mix of article ages.
    shards: List[List[OverviewRow]] = [[] for _ in range(n_conn)]
    for i, row in enumerate(rows):
        shards[i % n_conn].append(row)
    shards = [s for s in shards if s]
    n_conn = len(shards)

    logger.info(
        "Fetching %s articles with %s connection(s), pipeline depth %s",
        len(rows),
        n_conn,
        depth,
    )

    out_queue: queue.Queue = queue.Queue(maxsize=max(256, n_conn * depth * 2))
    threads = []
    for wid, shard in enumerate(shards):
        t = threading.Thread(
            target=_worker,
            name=f"nntp-fetch-{wid}",
            args=(wid, shard, group, conn_kwargs, depth, out_queue, stop_event),
            daemon=True,
        )
        threads.append(t)
        t.start()

    fetched_ok = 0
    missing = 0
    errors = 0
    done_workers = 0
    processed = 0
    t0 = time.monotonic()
    last_log = t0
    bytes_ok = 0

    while done_workers < n_conn:
        try:
            item = out_queue.get(timeout=1.0)
        except queue.Empty:
            if stop_event.is_set():
                break
            # Check for dead threads without sentinel (shouldn't happen).
            if not any(t.is_alive() for t in threads) and out_queue.empty():
                break
            continue

        if item is _WORKER_DONE:
            done_workers += 1
            continue

        row, content, resp = item
        on_article(row, content, resp)
        processed += 1
        if content:
            fetched_ok += 1
            bytes_ok += len(content)
        elif isinstance(resp, str) and resp.startswith("error:"):
            errors += 1
        else:
            missing += 1

        now = time.monotonic()
        if processed % progress_every == 0 or (now - last_log) >= 5.0:
            elapsed = max(now - t0, 1e-6)
            arts_per_s = processed / elapsed
            kib_per_s = (bytes_ok / 1024.0) / elapsed
            logger.info(
                "progress: %s/%s articles (%.1f art/s, %.1f KiB/s, ok=%s missing=%s err=%s)",
                processed,
                len(rows),
                arts_per_s,
                kib_per_s,
                fetched_ok,
                missing,
                errors,
            )
            last_log = now

    for t in threads:
        t.join(timeout=5)

    elapsed = max(time.monotonic() - t0, 1e-6)
    return fetched_ok, missing, errors, elapsed
