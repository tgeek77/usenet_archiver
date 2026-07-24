# Usenet Archiver

This repository contains tools for working with **text Usenet** data in two different contexts:

1. **`app/usenet_archiver.py`** — Connect to a remote NNTP service over TLS or plain NNTP, authenticate, and download articles from one or more newsgroups into Unix **mbox** files. Also supports listing groups, fetching by Message-ID, and posting (sinntp-style parity).
2. **`extras/`** — Bash helpers aimed at a **local news server** using **INN-style tradspool** storage under `/var/spool/news/articles/`, plus **`gz2mbox.py`** to turn `.gz` article dumps into mbox.

Nothing here is aimed at binary downloads or “NZB” workflows; the Python client is for **text archives**, research, and backups.

---

## Python archiver (`app/usenet_archiver.py`)

### Dependencies

Python **3.x**, **standard library only** (no `pip` packages).

### What it does

- Opens an NNTP connection (TLS by default, port **563**, or plain NNTP with **`--no-ssl`**, default port **119**).
- Discovers article ranges with **OVER / XOVER** (falling back to **XHDR DATE**), bisecting on `Date` and scanning overview chunks — no provider-specific retention heuristics.
- Optionally restricts downloads with **`--start-date`** and **`--end-date`** (`YYYY-MM-DD`). You may pass **only** `--start-date` (end defaults to **today, UTC**) or **only** `--end-date` (start defaults to **1990-01-01**). Passing **neither** fetches the full article-number range.
- Writes articles into an **mbox** file in **append** mode with **Message-ID deduplication** (resume-friendly). Appends the mbox filename to **`completed_newsgroups.log`** after a successful save so the same job can be skipped on rerun.
- Keeps article payloads as **bytes** end to end (ISO-8859-1 / KOI8-R / Shift_JIS bodies are not mangled).
- Missing articles (`430` / `423`) are skipped; the run continues (the crash that broke sinntp with `nntplib`).

Paths for `.mbox`, `.log`, and `completed_newsgroups.log` are **relative to where you run the command**.

### Credential and server resolution

| Source | Role |
|--------|------|
| `--server` / `$NNTPSERVER` / `/etc/news/server` | Host (and optional `:port`); exit code **2** if none found |
| `--username` / `--password` | Explicit credentials |
| `--password-file` | Password from a file (preferred over argv) |
| `$NNTP_PASSWORD` | Password from the environment |
| `~/.netrc` | Fallback login/password (disable with **`--no-netrc`**) |

Password precedence: **flag > password-file > env > netrc**.

`--server` accepts `host`, `host:port`, or `[ipv6]:port`.

### Usage

```bash
python3 app/usenet_archiver.py -h
```

### Options

| Option | Meaning |
|--------|---------|
| `--server` | NNTP hostname or `host:port` (optional if `$NNTPSERVER` / `/etc/news/server` set) |
| `--port` | Port (default: **563** with TLS, **119** with `--no-ssl`) |
| `--username`, `--password` | NNTP credentials (optional; see resolution above) |
| `--password-file` | Read password from file |
| `--no-netrc` | Ignore `~/.netrc` |
| `--newsgroup GROUP[>FILE]` | Group to fetch (repeatable; optional `group>filename`) |
| `--groups-file FILE` | One `group[>filename]` per line |
| `--no-ssl` | Plain NNTP instead of TLS |
| `--verbose` | Extra NNTP debugging on stderr |
| `--syslog` | Also log to syslog (`LOG_NEWS`) |
| `--timeout` | Socket timeout in seconds (default **60**) |
| `--start-date`, `--end-date` | Inclusive date window |
| `--overview-chunk N` | OVER/XOVER chunk size (default **10000**) |
| `--no-dedup` | Disable Message-ID deduplication |
| `--plugin SPEC` | Apply plugin (`name` or `name:arg:key=value`); repeatable |
| `--connections N` | Parallel NNTP connections for ARTICLE fetch (default **8**) |
| `--pipeline-depth N` | ARTICLE commands pipelined per connection before reading (default **32**) |
| `--list-groups [WILDMAT]` | List groups (optional wildmat) to stdout and exit |
| `--message-id ID` | Fetch one article by Message-ID to stdout |
| `--post` | Post one RFC 5322 message from stdin |

Overview discovery uses one connection; ARTICLE download fans out across `--connections` sockets, each pipelining `--pipeline-depth` requests. Raise both against a provider that allows many concurrent connections (e.g. `--connections 32 --pipeline-depth 64`). Progress lines report articles/sec and KiB/sec.

### Plugins

Built-ins (BSD-licensed):

| Plugin | Effect |
|--------|--------|
| `strip_headers` | Delete headers (default `To,Cc,Bcc`) |
| `mimify` | Add default `Content-Type` if missing |
| `keep_headers` | Keep only listed headers; clear body |
| `debug` | Print call args |

Example: `--plugin strip_headers:To,Cc --plugin mimify:charset=UTF-8`

### Examples

Pull with dates:

```bash
python3 app/usenet_archiver.py \
  --verbose \
  --server news.example.com \
  --username USER \
  --password-file ~/.nntp_pass \
  --newsgroup news.groups \
  --start-date 2021-01-01 \
  --end-date 2022-01-01 \
  --connections 32 \
  --pipeline-depth 64
```

Multiple groups / custom mbox names:

```bash
python3 app/usenet_archiver.py \
  --server news.example.com \
  --newsgroup 'comp.lang.python>python.mbox' \
  --newsgroup news.announce.newgroups
```

List / get / post:

```bash
python3 app/usenet_archiver.py --server news.example.com --list-groups 'comp.*'
python3 app/usenet_archiver.py --server news.example.com --message-id 'abc@example.com'
python3 app/usenet_archiver.py --server news.example.com --post < article.eml
```

TLS is the default; omit **`--no-ssl`** to keep TLS on port 563.

### Tests

```bash
python3 -m unittest discover -s tests -v
```

### Responsible use

Use a **provider where your subscription allows automated bulk reading**. Avoid hammering small free servers that exist for casual posting. Paid/block providers are commonly discussed in communities such as [r/usenet](https://www.reddit.com/r/usenet/).

---

## Extras (server-side, tradspool layout)

These scripts assume a **Linux** (or similar) news host with article files under **`/var/spool/news/articles/`**. Several commands rely on **GNU** utilities. They are optional and independent of the Python client.

| Script | Purpose |
|--------|---------|
| **`extras/archive.sh`** | Interactive: given calendar month/year, **`rsync`**’s matching directory mtimes into `/tmp`, rearranges the tree, **`zip`**’s to `/opt/usenet/`, appends sizes to `/opt/usenet/archivelog.txt`. Uses **padded month/day** datetimes, **leap years** for February, and **end-of-day** (`23:59:59`). |
| **`extras/report.sh`** | Counts articles per Big-8–style top-level tree and total spool size; writes a timestamped CSV-style report. Ensures **`${REPORT_DIR:-/srv/www/htdocs/reports}/archive`** exists. Override: `REPORT_DIR=/path ./extras/report.sh`. |
| **`extras/biggestgroups.sh`** | Ranks directories by number of immediate child entries; produces Big-8–filtered and global top-50 / top-1000 lists, expire-header grep, and optional **`unwanted.log`** copy. Same **`REPORT_DIR`** convention. |
| **`extras/Big-8_Report.sh`** | Smaller variant: Big-8 ranking only, written to **`$HOME`**. |
| **`extras/crosspost_report.sh`** | Lists each article path with a **group count** from the **`Newsgroups:`** header. Output **`$HOME/<timestamp>-sorted.csv`**. |
| **`extras/gz2mbox.py`** | Walk a tree of `.gz` Usenet article dumps and write one Thunderbird-compatible **mboxrd** file (locale-independent `From_` envelopes; shares helpers with `app/mboxout.py`). |

---

## Layout

```
app/usenet_archiver.py   # CLI entry point
app/nntp.py              # Byte-safe NNTP client (pipelined ARTICLE)
app/fetch.py             # Multi-connection parallel fetch
app/overview.py          # OVER/XOVER date discovery
app/mboxout.py           # mboxrd writer + Message-ID dedup
app/creds.py             # Server / credential resolution
app/plugins.py           # Message plugins
extras/*.sh              # Tradspool reporting and archival helpers
extras/gz2mbox.py        # gzip dumps → mbox
tests/                   # stdlib unittest suite
LICENSE                  # BSD 2-Clause
```

---

## License

BSD 2-Clause — see **`LICENSE`**.
