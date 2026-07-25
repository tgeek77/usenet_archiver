#!/usr/bin/env python3
"""Server and credential resolution for the Usenet archiver.

Precedence for password: explicit flag > password file > $NNTP_PASSWORD > ~/.netrc.
Server: --server > $NNTPSERVER > /etc/news/server.
"""

from __future__ import annotations

import netrc
import os
import re
from typing import NamedTuple, Optional, Tuple


_SPLIT_HOST_RE = re.compile(
    r"^ (?: \[ ( [^\[\]]+ ) \] | ( [^:]+ ) | ( .* ) ) (?: : ([0-9]+) )? $",
    re.VERBOSE,
)


class ResolvedEndpoint(NamedTuple):
    host: str
    port: Optional[int]
    username: Optional[str]
    password: Optional[str]


def split_host(host: str, default_port: Optional[int] = None) -> Tuple[str, Optional[int]]:
    """Parse host, host:port, or [ipv6]:port. BSD-licensed rewrite of sinntp's helper."""
    match = _SPLIT_HOST_RE.match(host)
    if match is None:
        raise ValueError(f"Invalid host specification: {host!r}")
    host1, host2, host3, port = match.groups()
    hostname = host1 or host2 or host3
    if port is None:
        return hostname, default_port
    return hostname, int(port)


def get_default_nntp_server() -> Optional[str]:
    """Resolve $NNTPSERVER, then /etc/news/server."""
    env = os.environ.get("NNTPSERVER")
    if env:
        return env.strip() or None
    try:
        with open("/etc/news/server", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except OSError:
        pass
    return None


def _netrc_lookup(hostname: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        nrc = netrc.netrc()
    except (OSError, netrc.NetrcParseError):
        return None, None
    # netrc matches on host; try exact then bare
    entry = nrc.authenticators(hostname)
    if entry is None:
        return None, None
    login, _account, password = entry
    return login, password


def resolve_credentials(
    server: Optional[str],
    port: Optional[int],
    username: Optional[str],
    password: Optional[str],
    password_file: Optional[str] = None,
    use_netrc: bool = True,
    use_ssl: bool = True,
) -> ResolvedEndpoint:
    """Resolve host/port/username/password with documented precedence.

    Raises SystemExit(2) when no server can be determined (caller may catch).
    """
    if not server:
        server = get_default_nntp_server()
    if not server:
        raise SystemExit(2)

    host, embedded_port = split_host(server, default_port=None)
    if port is None:
        port = embedded_port
    if port is None:
        port = 563 if use_ssl else 119

    resolved_user = username
    resolved_pass = password

    if resolved_pass is None and password_file:
        with open(password_file, encoding="utf-8") as fh:
            # Entire file is the password; a single trailing newline is ignored.
            resolved_pass = fh.read().rstrip("\n")

    if resolved_pass is None:
        env_pass = os.environ.get("NNTP_PASSWORD")
        if env_pass is not None:
            resolved_pass = env_pass

    if use_netrc and (resolved_user is None or resolved_pass is None):
        n_user, n_pass = _netrc_lookup(host)
        if resolved_user is None:
            resolved_user = n_user
        if resolved_pass is None:
            resolved_pass = n_pass

    from .policy import check_server_allowed

    check_server_allowed(host)

    return ResolvedEndpoint(host=host, port=port, username=resolved_user, password=resolved_pass)
