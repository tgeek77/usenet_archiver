"""Archiving policy: blocked servers and binary-group skips.

Extend ``SERVER_BLACKLIST`` and ``BINARY_GROUP_MARKERS`` below as needed.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

# Hostnames and DNS suffixes that must not be used for bulk archiving.
# Matching is case-insensitive: exact host, or host ending in ".<entry>".
# Eternal September bans accounts that abuse their low connection limits:
# https://www.eternal-september.org/index.php?showpage=techinfo
SERVER_BLACKLIST: List[str] = [
    "eternal-september.org",
    "news.eternal-september.org",
    "reader80.eternal-september.org",
    "reader443.eternal-september.org",
]

BLOCKED_SERVER_MESSAGE = "This server is not available for archiving"

# Substrings (case-insensitive) that mark a newsgroup as binary / not for text archive.
# Add misspellings and non-English forms here.
BINARY_GROUP_MARKERS: List[str] = [
    "binary",
    "binaries",
    "bainary",
    "binay",
    "binari",
    "binario",
    "binarios",
    "binaire",
    "binaires",
    "binaer",
    "binär",
    "バイナリ",
]


def is_server_blacklisted(host: str) -> bool:
    """Return True if *host* is on the archiving blacklist."""
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return False
    for entry in SERVER_BLACKLIST:
        e = entry.strip().lower().rstrip(".")
        if not e:
            continue
        if h == e or h.endswith("." + e):
            return True
    return False


def check_server_allowed(host: str) -> None:
    """Raise ``ValueError`` with ``BLOCKED_SERVER_MESSAGE`` if blacklisted."""
    if is_server_blacklisted(host):
        raise ValueError(BLOCKED_SERVER_MESSAGE)


def is_binary_newsgroup(group: str) -> bool:
    """Return True if the group name looks like a binary group."""
    g = (group or "").lower()
    if not g:
        return False
    return any(marker.lower() in g for marker in BINARY_GROUP_MARKERS)


def filter_group_specs(
    specs: Sequence[Tuple[str, Optional[str]]],
) -> Tuple[List[Tuple[str, Optional[str]]], List[str]]:
    """Drop binary groups from *specs*.

    Returns ``(kept_specs, skipped_group_names)``.
    """
    kept: List[Tuple[str, Optional[str]]] = []
    skipped: List[str] = []
    for group, filename in specs:
        if is_binary_newsgroup(group):
            skipped.append(group)
        else:
            kept.append((group, filename))
    return kept, skipped


def read_groups_file(path: str) -> List[str]:
    """Read one newsgroup name per line (# comments and blanks ignored)."""
    groups: List[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Allow optional group>filename; keep full line for callers that parse it.
            groups.append(line)
    return groups
