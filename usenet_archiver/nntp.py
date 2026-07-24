#!/usr/bin/env python3
"""Byte-safe NNTP client (stdlib sockets + optional TLS).

Article payloads are kept as bytes end to end. Only ASCII status lines are
decoded for control flow, so ISO-8859-1 / KOI8-R / Shift_JIS bodies survive.
"""

from __future__ import annotations

import logging
import socket
import ssl
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


class NNTPTimeout(Exception):
    """Raised when an NNTP socket read exceeds the configured timeout."""


class NNTPError(Exception):
    """Raised for unexpected NNTP protocol responses."""


class NNTPClient:
    def __init__(
        self,
        server: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: bool = True,
        verbose: bool = False,
        timeout: int = 60,
    ):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.verbose = verbose
        self.timeout = timeout
        self.conn: Optional[socket.socket] = None
        self._buf = b""
        self.capabilities: Dict[str, List[str]] = {}
        self.logger = logging.getLogger(__name__)
        if verbose:
            self.logger.setLevel(logging.DEBUG)

    # --- transport ---------------------------------------------------------

    def connect(self) -> None:
        try:
            sock = socket.create_connection((self.server, self.port), timeout=self.timeout)
            sock.settimeout(self.timeout)
            if self.use_ssl:
                context = ssl.create_default_context()
                sock = context.wrap_socket(sock, server_hostname=self.server)
            self.conn = sock
            self._buf = b""

            welcome = self._recv_status()
            if self.verbose:
                print(f"Welcome: {welcome}")

            if self.username and self.password:
                self.send(f"AUTHINFO USER {self.username}")
                user_resp = self._recv_status()
                if self.verbose:
                    print(f"USER response: {user_resp}")

                self.send(f"AUTHINFO PASS {self.password}")
                auth_resp = self._recv_status()
                if self.verbose:
                    print(f"PASS response: {auth_resp}")
                if not auth_resp.startswith("281"):
                    raise NNTPError(f"Authentication failed: {auth_resp}")

            self.send("MODE READER")
            mode_resp = self._recv_status()
            if self.verbose:
                print(f"MODE response: {mode_resp}")

            self.capabilities = self._probe_capabilities()
        except NNTPError:
            self.close()
            raise
        except Exception as e:
            self.close()
            raise NNTPError(f"Connection error: {e}") from e

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except OSError:
                pass
            self.conn = None
        self._buf = b""

    def quit(self) -> None:
        try:
            if self.conn is not None:
                self.send("QUIT")
                try:
                    self._recv_status()
                except Exception:
                    pass
        finally:
            self.close()

    def send(self, command: str) -> None:
        if self.conn is None:
            raise NNTPError("Not connected")
        self.conn.settimeout(self.timeout)
        self.conn.sendall(f"{command}\r\n".encode("ascii", errors="strict"))

    def _recv_raw(self, nbytes: int = 8192) -> bytes:
        if self.conn is None:
            raise NNTPError("Not connected")
        self.conn.settimeout(self.timeout)
        try:
            data = self.conn.recv(nbytes)
        except socket.timeout as e:
            raise NNTPTimeout("The read operation timed out") from e
        if not data:
            raise NNTPError("Connection closed by server")
        return data

    def _readline(self) -> bytes:
        """Read one CRLF-terminated line as bytes (CRLF stripped)."""
        while True:
            nl = self._buf.find(b"\n")
            if nl >= 0:
                line = self._buf[:nl]
                self._buf = self._buf[nl + 1 :]
                if line.endswith(b"\r"):
                    line = line[:-1]
                return line
            self._buf += self._recv_raw()

    def _recv_status(self) -> str:
        line = self._readline()
        try:
            return line.decode("ascii", errors="replace").strip()
        except Exception:
            return line.decode("latin-1", errors="replace").strip()

    def _read_multiline(self) -> List[bytes]:
        """Read an RFC 3977 dot-terminated multiline response; unstuflines."""
        lines: List[bytes] = []
        for line in self._iter_multiline():
            lines.append(line)
        return lines

    def _iter_multiline(self) -> Iterable[bytes]:
        while True:
            line = self._readline()
            if line == b".":
                return
            if line.startswith(b"."):
                line = line[1:]
            yield line

    def recv_article_body(self) -> bytes:
        """Read a multiline article body with timeout retries; return joined bytes."""
        retries = 3
        while retries > 0:
            try:
                parts = list(self._iter_multiline())
                return b"\n".join(parts)
            except NNTPTimeout:
                retries -= 1
                if retries == 0:
                    raise NNTPTimeout("The read operation timed out after retries")
                self.logger.warning("Timeout in recv_article_body, retries left: %s", retries)
                time.sleep(1)
                # After a timeout the stream is desynchronized; caller must reconnect.
                raise

    # --- protocol helpers --------------------------------------------------

    def _probe_capabilities(self) -> Dict[str, List[str]]:
        caps: Dict[str, List[str]] = {}
        try:
            self.send("CAPABILITIES")
            resp = self._recv_status()
            if not resp.startswith("101"):
                return caps
            for raw in self._read_multiline():
                try:
                    text = raw.decode("ascii", errors="replace").strip()
                except Exception:
                    continue
                if not text:
                    continue
                parts = text.split()
                name = parts[0].upper()
                caps[name] = parts[1:]
        except Exception as e:
            self.logger.debug("CAPABILITIES probe failed: %s", e)
        return caps

    def has_capability(self, name: str) -> bool:
        return name.upper() in self.capabilities

    def group(self, newsgroup: str) -> Tuple[int, int, str]:
        self.send(f"GROUP {newsgroup}")
        resp = self._recv_status()
        if self.verbose:
            print(f"GROUP response: {resp}")
        if not resp.startswith("211"):
            raise NNTPError(f"Failed to select group {newsgroup}: {resp}")
        parts = resp.split()
        if len(parts) < 4:
            raise NNTPError(f"Invalid GROUP response: {resp}")
        first, last = int(parts[2]), int(parts[3])
        return first, last, resp

    def stat(self, article_id: int) -> Tuple[int, str]:
        self.send(f"STAT {article_id}")
        resp = self._recv_status()
        if self.verbose:
            print(f"STAT {article_id} response: {resp}")
        if resp.startswith("223"):
            parts = resp.split()
            if len(parts) < 2:
                raise NNTPError(f"Invalid STAT response: {resp}")
            return int(parts[1]), resp
        return 0, resp

    def article(self, article_spec) -> Tuple[bytes, str]:
        """Fetch ARTICLE by number or Message-ID. Empty bytes if missing."""
        results = self.articles_pipelined([article_spec])
        _spec, content, resp = results[0]
        return content, resp

    def articles_pipelined(
        self, article_specs: Sequence
    ) -> List[Tuple[object, bytes, str]]:
        """Pipeline ARTICLE commands, then read responses in order (RFC 3977).

        Sends all requests in ``article_specs`` before reading any response,
        which hides per-article round-trip latency. Returns one triple per
        input: ``(spec, content_bytes, status_line)``. Missing articles yield
        empty ``content_bytes``.
        """
        if not article_specs:
            return []
        # Send the whole batch first.
        for spec in article_specs:
            self.send(f"ARTICLE {spec}")
        results: List[Tuple[object, bytes, str]] = []
        for spec in article_specs:
            resp = self._recv_status()
            if self.verbose:
                print(f"ARTICLE {spec} response: {resp}")
            if not resp.startswith("220"):
                results.append((spec, b"", resp))
                continue
            content = b"\n".join(self._read_multiline())
            if self.verbose and content:
                print(f"Fetched article {spec} (first 100 bytes): {content[:100]!r}...")
            results.append((spec, content, resp))
        return results

    def over(self, start_id: int, end_id: int) -> Tuple[List[bytes], str, str]:
        """Issue OVER or XOVER for an article-number range.

        Returns (lines, command_used, status_response).
        """
        commands: Sequence[str] = ("OVER", "XOVER")
        # Prefer OVER when advertised; still try both.
        if self.has_capability("OVER") or self.has_capability("XOVER"):
            if not self.has_capability("OVER") and self.has_capability("XOVER"):
                commands = ("XOVER", "OVER")
        last_resp = ""
        for cmd in commands:
            self.send(f"{cmd} {start_id}-{end_id}")
            resp = self._recv_status()
            last_resp = resp
            if self.verbose:
                print(f"{cmd} {start_id}-{end_id} response: {resp}")
            if resp.startswith("224"):
                return self._read_multiline(), cmd, resp
            # 500/501/502 = not supported; try next
            if resp.startswith(("500", "501", "502")):
                continue
            # Other errors (e.g. empty range): return empty
            return [], cmd, resp
        return [], "", last_resp

    def xhdr_date(self, start_id: int, end_id: int) -> List[Tuple[int, str]]:
        """XHDR DATE fallback; returns list of (article_id, date_string)."""
        self.send(f"XHDR DATE {start_id}-{end_id}")
        resp = self._recv_status()
        if self.verbose:
            print(f"XHDR DATE {start_id}-{end_id} response: {resp}")
        if not resp.startswith("221"):
            self.logger.warning("XHDR DATE not supported or failed: %s", resp)
            return []
        result: List[Tuple[int, str]] = []
        for raw in self._read_multiline():
            try:
                line = raw.decode("ascii", errors="replace")
            except Exception:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2 and parts[0].isdigit():
                result.append((int(parts[0]), parts[1].strip()))
        return result

    def list_active(self, wildmat: Optional[str] = None) -> List[str]:
        """LIST ACTIVE [wildmat], falling back to LIST. Returns group names."""
        if wildmat:
            cmd = f"LIST ACTIVE {wildmat}"
        else:
            cmd = "LIST ACTIVE"
        self.send(cmd)
        resp = self._recv_status()
        if not resp.startswith("215"):
            # Fall back to bare LIST
            self.send("LIST")
            resp = self._recv_status()
            if not resp.startswith("215"):
                raise NNTPError(f"LIST failed: {resp}")
        names: List[str] = []
        for raw in self._read_multiline():
            try:
                text = raw.decode("utf-8", errors="surrogateescape").strip()
            except Exception:
                continue
            if not text:
                continue
            name = text.split()[0]
            names.append(name)
        return names

    def post(self, message: bytes) -> str:
        """POST a raw RFC 5322 message (bytes). Returns the final status line."""
        self.send("POST")
        resp = self._recv_status()
        if not resp.startswith("340"):
            raise NNTPError(f"POST rejected: {resp}")
        if self.conn is None:
            raise NNTPError("Not connected")
        # Dot-stuff lines beginning with '.'
        lines = message.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
        stuffed: List[bytes] = []
        for line in lines:
            if line.startswith(b"."):
                stuffed.append(b"." + line)
            else:
                stuffed.append(line)
        payload = b"\r\n".join(stuffed)
        if not payload.endswith(b"\r\n"):
            payload += b"\r\n"
        payload += b".\r\n"
        self.conn.settimeout(self.timeout)
        self.conn.sendall(payload)
        final = self._recv_status()
        if not final.startswith("240"):
            raise NNTPError(f"POST failed: {final}")
        return final
