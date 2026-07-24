#!/usr/bin/env python3
"""BSD-licensed message plugins for the Usenet archiver.

Each plugin is a callable(message=email.message.Message, **kwargs) -> Message | None.
Returning None drops the message from the output.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, List, Optional

from email.message import Message


def debug(*args, message: Optional[Message] = None, **kwargs):
    print(f"debug(*{args!r}, **{kwargs!r})")
    return message


def strip_headers(headers: str = "To,Cc,Bcc", message: Optional[Message] = None):
    """Delete the named headers (comma-separated)."""
    if message is None:
        return None
    for header in headers.split(","):
        header = header.strip()
        if header:
            try:
                del message[header]
            except KeyError:
                pass
    return message


def mimify(type: str = "text/plain", charset: str = "US-ASCII", message: Optional[Message] = None):
    """Add a default Content-Type when missing."""
    if message is None:
        return None
    if "Content-Type" not in message:
        message["Content-Type"] = f"{type}; charset={charset}"
    return message


def keep_headers(headers: str = "From,Subject,Date,Message-ID,Newsgroups,References,In-Reply-To",
                 message: Optional[Message] = None):
    """Retain only the listed headers (header-only archive). Body is cleared."""
    if message is None:
        return None
    keep = {h.strip().lower() for h in headers.split(",") if h.strip()}
    # Collect values first (case-insensitive match on header names)
    retained = []
    for key, value in message.items():
        if key.lower() in keep:
            retained.append((key, value))
    # Clear all headers
    for key in list(message.keys()):
        del message[key]
    for key, value in retained:
        message[key] = value
    message.set_payload("")
    return message


_BUILTIN = {
    "debug": debug,
    "strip_headers": strip_headers,
    "mimify": mimify,
    "keep_headers": keep_headers,
}


def parse_plugin_spec(spec: str) -> Callable[[Message], Optional[Message]]:
    """Parse ``name`` or ``name:arg:arg:key=value`` into a partial callable.

    Positional args before any key=value become *args; key=value become kwargs.
    The resulting callable accepts only ``message=``.
    """
    parts = spec.split(":")
    name = parts[0]
    if name not in _BUILTIN:
        raise ValueError(f"Unknown plugin: {name!r} (available: {', '.join(sorted(_BUILTIN))})")
    func = _BUILTIN[name]
    args: List[Any] = []
    kwargs: dict = {}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            kwargs[key] = value
        else:
            args.append(part)
    return functools.partial(func, *args, **kwargs)


def apply_plugins(message: Message, plugins: List[Callable[[Message], Optional[Message]]]) -> Optional[Message]:
    """Run plugins in order; stop and drop if any returns None."""
    for plugin in plugins:
        message = plugin(message=message)  # type: ignore[call-arg, arg-type]
        if message is None:
            return None
    return message


__all__ = [
    "debug",
    "mimify",
    "strip_headers",
    "keep_headers",
    "parse_plugin_spec",
    "apply_plugins",
]
