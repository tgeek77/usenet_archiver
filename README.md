# Usenet Archiver

Tools for **text Usenet** archives:

1. **`usenet_archiver/`** — NNTP client package (TLS/plain, OVER-based date discovery, multi-connection ARTICLE fetch → mbox).
2. **`gui/usenet_archiver_gui.py`** — Tkinter GUI for pull jobs (githelper-style).
3. **`extras/`** — Local INN tradspool helpers + **`gz2mbox.py`**.

Nothing here is aimed at binary/NZB workflows.

---

## Install / run (single-file zipapp)

Same pattern as sword-cli: build one executable zipapp, copy onto `$PATH`.

```bash
make zipapp
sudo cp dist/usenet-archiver /usr/local/bin/
usenet-archiver --help
```

### Development

```bash
./bin/usenet-archiver --help          # prefers .venv if present
python3 -m usenet_archiver --help
python3 app/usenet_archiver.py --help # back-compat shim
make gui                              # Tkinter GUI
```

Optional: `pip install .` installs the `usenet-archiver` console script (stdlib only; no deps).

### Dependencies

Python **3.9+**, **standard library only** (no `pip` packages required for the CLI). The GUI needs Tk (`python3-tk` on some distros).

---

## What the CLI does

- Opens NNTP (TLS default port **563**, or **`--no-ssl`** port **119**).
- Discovers article ranges with **OVER / XOVER** (fallback **XHDR DATE**).
- Fetches with **`--connections`** parallel sockets and **`--pipeline-depth`** pipelined `ARTICLE` commands.
- Date window via **`--start-date`** / **`--end-date`** (`YYYY-MM-DD`). Omit end → through **today UTC**; omit start → from **1990-01-01**. Open-ended "since DATE" jobs include today's date in the mbox name, so the same request tomorrow is a **new pull**.
- Writes **mbox** in **append** mode with **Message-ID dedup**; records a job in **`completed_newsgroups.log` only after a successful, complete pull** (cancelled / errored runs are not recorded). Re-running is safe and **incremental** via Message-ID dedup. Use **`--skip-completed`** to hard-skip jobs already listed.
- Article payloads stay **bytes** end to end; missing articles (`430`/`423`) are skipped.

Paths for `.mbox`, `.log`, and `completed_newsgroups.log` are relative to the working directory.

### Credential and server resolution

| Source | Role |
|--------|------|
| `--server` / `$NNTPSERVER` / `/etc/news/server` | Host (optional `:port`); exit **2** if missing |
| `--username` / `--password` | Explicit credentials |
| `--password-file` | Password from a file (prefer over argv) |
| `$NNTP_PASSWORD` | Password from the environment |
| `~/.netrc` | Fallback (disable with **`--no-netrc`**) |

Password precedence: **flag > password-file > env > netrc**.

### Options

| Option | Meaning |
|--------|---------|
| `--server` | Hostname or `host:port` |
| `--port` | Port (default **563** TLS / **119** plain) |
| `--username`, `--password` | Credentials (prefer `--password-file`) |
| `--password-file` | Read password from file |
| `--no-netrc` | Ignore `~/.netrc` |
| `--newsgroup GROUP[>FILE]` | Group (repeatable; optional `group>filename`) |
| `--groups-file FILE` | One `group[>filename]` per line |
| `--no-ssl` | Plain NNTP |
| `--verbose` / `--syslog` | Logging |
| `--timeout` | Socket timeout (default **60**) |
| `--start-date`, `--end-date` | Inclusive date window |
| `--overview-chunk N` | OVER/XOVER chunk size (default **10000**) |
| `--no-dedup` | Disable Message-ID dedup |
| `--plugin SPEC` | Plugin (`name` or `name:arg:key=value`) |
| `--connections N` | Parallel NNTP connections (default **8**) |
| `--pipeline-depth N` | Pipelined ARTICLEs per connection (default **32**) |
| `--list-groups [WILDMAT]` | List groups and exit |
| `--message-id ID` | Fetch one article to stdout |
| `--post` | Post one RFC 5322 message from stdin |

### Example

```bash
usenet-archiver \
  --server news.example.com \
  --username USER \
  --password-file ~/.nntp_pass \
  --newsgroup news.groups \
  --start-date 2021-01-01 \
  --end-date 2022-01-01 \
  --connections 32 \
  --pipeline-depth 64
```

### Plugins

| Plugin | Effect |
|--------|--------|
| `strip_headers` | Delete headers (default `To,Cc,Bcc`) |
| `mimify` | Default `Content-Type` if missing |
| `keep_headers` | Keep listed headers; clear body |
| `debug` | Print call args |

### Tests

```bash
make test
# or
python3 -m unittest discover -s tests -v
```

### Responsible use

Use a provider that allows automated bulk reading. Avoid hammering small free servers.

---

## GUI

```bash
make gui
# or
python3 gui/usenet_archiver_gui.py
```

Tkinter form for connection, credentials (prefer **password file**), newsgroup, dates, connections/pipeline, and output directory. Runs the pull in a **background thread** with a status line, indeterminate progress bar, scrollable log, and **Stop**. Settings save to **`~/.usenet_archiverrc`** (mode `0600`); the password field itself is not written to that file.

---

## Extras (tradspool)

| Script | Purpose |
|--------|---------|
| **`extras/archive.sh`** | Monthly spool zip under `/opt/usenet/` |
| **`extras/report.sh`** | Hierarchy size report (`REPORT_DIR`) |
| **`extras/biggestgroups.sh`** | Top groups / expire / unwanted |
| **`extras/Big-8_Report.sh`** | Big-8 ranking → `$HOME` |
| **`extras/crosspost_report.sh`** | Crosspost counts CSV |
| **`extras/gz2mbox.py`** | `.gz` article dumps → mboxrd |

---

## Layout

```
usenet_archiver/         # Installable package (CLI + library)
  cli.py                 # argparse entry (run / main)
  nntp.py fetch.py …     # NNTP, parallel fetch, overview, mbox, creds, plugins
gui/usenet_archiver_gui.py
bin/usenet-archiver      # Dev launcher
scripts/build_zipapp.sh  # → dist/usenet-archiver
app/usenet_archiver.py   # Back-compat shim
extras/                  # Tradspool helpers + gz2mbox
tests/
Makefile
pyproject.toml
LICENSE                  # BSD 2-Clause
```

---

## License

BSD 2-Clause — see **`LICENSE`**.
