# Usenet Archiver

Tools for **text Usenet** archives:

1. **`usenet_archiver/`** — NNTP client package + Tk GUI (TLS/plain, OVER-based date discovery, multi-connection ARTICLE fetch → mbox).
2. **`extras/`** — Local INN tradspool helpers + **`gz2mbox.py`**.

Nothing here is aimed at binary/NZB workflows.

---

## Releases

| Platform | Artifact |
|----------|----------|
| **Linux** | AppImage (`Usenet_Archiver-<ver>-x86_64.AppImage`) |
| **OpenBSD / macOS / other** | Zipapp tarball (`usenet-archiver-<ver>-zipapp.tar.gz`) |

GitHub Actions publishes both on tags matching `v*` (e.g. `v2.0.1`).

```bash
# Linux AppImage
chmod +x Usenet_Archiver-*-x86_64.AppImage
./Usenet_Archiver-*-x86_64.AppImage          # GUI
./Usenet_Archiver-*-x86_64.AppImage -c pull --help  # CLI
./Usenet_Archiver-*-x86_64.AppImage --help            # help (no -c)

# Zipapp tarball (needs Python 3.9+ on PATH)
tar xzf usenet-archiver-*-zipapp.tar.gz
./usenet-archiver              # GUI (needs Tk)
./usenet-archiver -c --help    # CLI subcommands
./usenet-archiver -c pull -h   # pull options
```

OpenBSD: `pkg_add python3` (and the Tk bindings for your Python if you want the GUI).

---

## Install / run (local zipapp)

```bash
make zipapp
sudo cp dist/usenet-archiver /usr/local/bin/
usenet-archiver                # GUI
usenet-archiver --help         # help (no -c)
usenet-archiver -c pull --help # CLI
```

`make appimage` builds the Linux AppImage locally (needs `python3-tk`, linuxdeploy, appimagetool).

### Development

```bash
./bin/usenet-archiver --help       # help (no -c needed)
./bin/usenet-archiver --version
./bin/usenet-archiver              # GUI (prefers .venv if present)
./bin/usenet-archiver -c pull -s news.example.com -g news.groups -n
python3 -m usenet_archiver -c pull --help
make gui                           # same as python3 -m usenet_archiver
```

Optional: `pip install .` installs the `usenet-archiver` console script (stdlib only; no deps).

### Dependencies

Python **3.9+**, **standard library only** (no `pip` packages required for the CLI). The GUI needs Tk (`python3-tk` on Debian/Ubuntu; OpenBSD Tk packages for your Python). Use **`-c`** for CLI-only when Tk is missing.

---

## What the CLI does

Invoke with **`-c`** and a **subcommand**:

```bash
usenet-archiver -c pull -s news.example.com -g news.groups ...
usenet-archiver -c list-groups 'comp.*'
usenet-archiver -c get '<mid@example.com>'
usenet-archiver -c post -g misc.test < msg.eml
```

| Command | Purpose |
|---------|---------|
| **`pull`** | Fetch articles into mbox (default archiving path) |
| **`list-groups`** | List newsgroups (optional wildmat) |
| **`get`** | Fetch one article by Message-ID to stdout |
| **`post`** | Post one RFC 5322 message from stdin |

`pull` behavior:

- Opens NNTP (TLS default port **563**, or **`--no-ssl`** port **119**).
- Discovers article ranges with **OVER / XOVER** (fallback **XHDR DATE**).
- Fetches with **`--connections`** parallel sockets and **`--pipeline-depth`** pipelined `ARTICLE` commands.
- Date window via **`--start-date`** / **`--end-date`** (`YYYY-MM-DD`). Omit end → through **today UTC**; omit start → from **1990-01-01**. Open-ended "since DATE" jobs include today's date in the mbox name, so the same request tomorrow is a **new pull**.
- Writes **mbox** in **append** mode with **Message-ID dedup**; records a job in **`completed_newsgroups.log` only after a successful, complete pull** (cancelled / errored runs are not recorded). Re-running is safe and **incremental** via Message-ID dedup. Use **`--skip-completed`** to hard-skip jobs already listed.
- Article payloads stay **bytes** end to end; missing articles (`430`/`423`) are skipped.
- Newsgroup names containing **binary** (and common misspellings / translations) are **skipped** automatically.
- Some servers are **blacklisted** for archiving (see below); the tool refuses them with *This server is not available for archiving*.
- **`--dry-run` / `-n`** does everything except downloading article bodies: connect, `GROUP`, overview date scan, Message-ID dedup against an existing mbox. It does **not** fetch `ARTICLE`, append to the mbox, or update `completed_newsgroups.log`.

Paths for `.mbox`, `.log`, and `completed_newsgroups.log` are relative to the working directory.

### Password file

`--password-file` / the GUI “Password file” field must point to a **plain-text file whose entire contents are the NNTP password**. One line is recommended; a single trailing newline is ignored. Do not put a username or other fields in that file (use `--username` / the Username field separately, or `~/.netrc`).

### Server blacklist

Bulk archiving is blocked for hosts that are known to ban automation for rate-limit abuse. The list lives in [`usenet_archiver/policy.py`](usenet_archiver/policy.py) as `SERVER_BLACKLIST` (easy to extend). Currently includes **Eternal September** hosts ([tech info](https://www.eternal-september.org/index.php?showpage=techinfo)): `news.eternal-september.org`, `reader80.eternal-september.org`, `reader443.eternal-september.org`, and any subdomain of `eternal-september.org`.

### Credential and server resolution

| Source | Role |
|--------|------|
| `--server` / `$NNTPSERVER` / `/etc/news/server` | Host (optional `:port`); exit **2** if missing |
| `--username` / `--password` | Explicit credentials |
| `--password-file` | Password from a file (prefer over argv) |
| `$NNTP_PASSWORD` | Password from the environment |
| `~/.netrc` | Fallback (disable with **`--no-netrc`**) |

Password precedence: **flag > password-file > env > netrc**.

### Options (shared + `pull`)

Connection flags apply to every subcommand. Archiving flags apply to **`pull`**.
Short and long forms are interchangeable (e.g. `-s` / `--server`, `-u` / `--user`).

| Option | Meaning |
|--------|---------|
| `-s`, `--server` | Hostname or `host:port` |
| `-P`, `--port` | Port (default **563** TLS / **119** plain) |
| `-u`, `--user`, `--username` | Username |
| `--password` | Password (prefer `--password-file`) |
| `--password-file`, `--pass-file` | Plain-text file containing only the password |
| `--no-netrc` | Ignore `~/.netrc` |
| `-g`, `--group`, `--newsgroup` | Group (repeatable; optional `group>filename`) |
| `-f`, `--file`, `--groups-file` | One `group[>filename]` per line |
| `--no-ssl` | Plain NNTP |
| `-v`, `--verbose` / `--syslog` | Logging |
| `-t`, `--timeout` | Socket timeout (default **60**) |
| `--start`, `--start-date` / `--end`, `--end-date` | Inclusive date window |
| `--overview-chunk N` | OVER/XOVER chunk size (default **10000**) |
| `--no-dedup` | Disable Message-ID dedup |
| `--plugin SPEC` | Plugin (`name` or `name:arg:key=value`) |
| `-C`, `--connections N` | Parallel NNTP connections (default **8**) |
| `-D`, `--depth`, `--pipeline-depth N` | Pipelined ARTICLEs per connection (default **32**) |
| `--skip-completed` | Skip jobs already in `completed_newsgroups.log` |
| `-n`, `--dry-run` | Connect + overview + dedup plan only (no ARTICLE / mbox write) |
| `-V`, `--version` | Print version and exit |

See `usenet-archiver -c COMMAND --help` for per-command details.

### Example

```bash
usenet-archiver -c pull \
  -s news.example.com \
  -u USER \
  --pass-file ~/.nntp_pass \
  -g news.groups \
  --start 2021-01-01 \
  --end 2022-01-01 \
  -C 32 \
  -D 64
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

Default when you run `usenet-archiver` (or `python3 -m usenet_archiver`) with no `-c`.

Tkinter form for connection, credentials (prefer **password file** — see above), a **queue of newsgroups** (Add / Import list / Remove), dates, connections/pipeline, and output directory. Import accepts one newsgroup per line (`#` comments allowed). **Run pull** downloads; **Dry run** only plans (overview + dedup counts in the log). Runs work in a **background thread** with a status line, indeterminate progress bar, scrollable log, and **Stop**. Settings save to **`~/.usenet_archiverrc`** (mode `0600`); the password field itself is not written to that file.

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
usenet_archiver/         # Installable package (GUI + CLI + library)
  app.py                 # Entry: GUI default, -c → CLI
  gui.py                 # Tkinter GUI
  cli.py                 # argparse CLI
  policy.py              # Server blacklist + binary-group skips
  nntp.py fetch.py …     # NNTP, parallel fetch, overview, mbox, creds, plugins
gui/usenet_archiver_gui.py  # Thin back-compat shim
bin/usenet-archiver      # Dev launcher
scripts/build_zipapp.sh  # → dist/usenet-archiver + *-zipapp.tar.gz
scripts/build_appimage.sh
assets/                  # App icon for AppImage
app/usenet_archiver.py   # Back-compat shim
extras/                  # Tradspool helpers + gz2mbox
.github/workflows/       # Release: AppImage + zipapp tarball
tests/
Makefile
pyproject.toml
LICENSE                  # BSD 2-Clause
```

---

## Changelog

### 2.0.1 — 2026-07-25

**Packaging & entry**
- Default launch is the **Tk GUI**; use **`-c`** for the CLI.
- **`--help`** / **`-h`** and **`--version`** / **`-V`** work without `-c`.
- Single-file **zipapp** plus versioned **zipapp tarball**; Linux **AppImage** build script and GitHub Actions release workflow (`v*` tags).

**CLI**
- Subcommands: **`pull`**, **`list-groups`**, **`get`**, **`post`** (shared connection flags on each).
- Short/long aliases for common options (`-s`/`--server`, `-u`/`--user`/`--username`, `-g`/`--group`/`--newsgroup`, `-f`/`--file`, `--start`/`--end`, `-C`/`--connections`, `-D`/`--depth`, `-n`/`--dry-run`, `--pass-file`, …).
- **`--dry-run` / `-n`**: connect, overview scan, Message-ID dedup plan — no `ARTICLE` download, mbox write, or completed-log update.
- **`--skip-completed`** is opt-in; re-pulls are incremental via Message-ID dedup by default.
- `completed_newsgroups.log` is updated only after a **successful, complete** pull (not on cancel/errors/partial runs).

**GUI**
- Server + port on one row; username + password on one row (port limited to 6 digits).
- Newsgroup **queue** with Add / Import / Remove / Clear (one group per line in import files).
- **Dry run** button alongside Run pull.
- Password-file format explained in the form and About tab.
- Settings still saved to `~/.usenet_archiverrc` (mode `0600`).

**Safety / policy** (`usenet_archiver/policy.py`)
- **Server blacklist** including Eternal September hosts; blocked with *This server is not available for archiving* (list is easy to extend).
- Newsgroups whose names look **binary** (`binary`, `bainary`, `binario`, …) are skipped automatically.

---

## License

BSD 2-Clause — see **`LICENSE`**.
