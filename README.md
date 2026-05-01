# Usenet Archiver

This repository contains tools for working with **text Usenet** data in two different contexts:

1. **`app/usenet_archiver.py`** — Connect to a remote NNTP service over TLS or plain NNTP, authenticate, and download articles from one newsgroup into a Unix **mbox** file.
2. **`extras/`** — Bash helpers aimed at a **local news server** using **INN-style tradspool** storage under `/var/spool/news/articles/` (counts, ranking groups, monthly snapshots, crosspost stats).

Nothing here is aimed at binary downloads or “NZB” workflows; the Python client is for **text archives**, research, and backups.

---

## Python archiver (`app/usenet_archiver.py`)

### Dependencies

Python **3.x**, **standard library only** (no `pip` packages).

### What it does

- Opens an NNTP connection (TLS by default, port **563**, or plain NNTP with **`--no-ssl`**, default port **119**).
- Optionally restricts downloads with **`--start-date`** and **`--end-date`** (format **`YYYY-MM-DD`**). You may pass **only** `--start-date` (end defaults to **today, UTC**) or **only** `--end-date` (start defaults to **1990-01-01**). Passing **neither** fetches the full article-number range (no date filter in the initial range logic).
- Writes articles into an **mbox** file and writes a **`.log`** file next to it (filenames include the date range when dates are used).
- Appends the mbox filename to **`completed_newsgroups.log`** in the **current working directory** after a successful run so the same job can be skipped on rerun (remove the line from that file if you want to redownload).

Paths for `.mbox`, `.log`, and `completed_newsgroups.log` are **relative to where you run the command**.

### Usage

```bash
python3 app/usenet_archiver.py -h
```

```
usage: usenet_archiver.py [-h] --server SERVER [--port PORT]
                          --username USERNAME --password PASSWORD
                          --newsgroup NEWSGROUP [--no-ssl] [--verbose]
                          [--timeout TIMEOUT] [--start-date START_DATE]
                          [--end-date END_DATE]

Fetch NNTP articles and save to mbox
```

| Option | Meaning |
|--------|---------|
| `--server` | NNTP hostname |
| `--port` | Port (default: **563** with TLS, **119** with `--no-ssl`) |
| `--username`, `--password` | NNTP credentials |
| `--newsgroup` | Group name (e.g. `news.groups`) |
| `--no-ssl` | Plain NNTP instead of TLS |
| `--verbose` | Extra NNTP debugging on stderr |
| `--timeout` | Socket timeout in seconds (default **60**) |
| `--start-date`, `--end-date` | Inclusive date window; either may be omitted (**defaults**: missing end → today UTC; missing start → 1990-01-01) |

### Example

```bash
python3 app/usenet_archiver.py \
  --verbose \
  --server news.example.com \
  --username USER \
  --password PASS \
  --newsgroup news.groups \
  --timeout 60 \
  --start-date 2021-01-01 \
  --end-date 2022-01-01
```

TLS is the default; omit **`--no-ssl`** to keep TLS on port 563.

### Responsible use

Use a **provider where your subscription allows automated bulk reading**. Avoid hammering small free servers that exist for casual posting. Paid/block providers are commonly discussed in communities such as [r/usenet](https://www.reddit.com/r/usenet/).

---

## Extras (server-side, tradspool layout)

These scripts assume a **Linux** (or similar) news host with article files under **`/var/spool/news/articles/`**. Several commands rely on **GNU** utilities (**GNU find** `-printf`, **`date -d`** not required but paths are GNU-centric). They are optional and independent of the Python client.

| Script | Purpose |
|--------|---------|
| **`extras/archive.sh`** | Interactive: given calendar month/year, **`rsync`**’s matching directory mtimes into `/tmp`, rearranges the tree, **`zip`**’s to `/opt/usenet/`, appends sizes to `/opt/usenet/archivelog.txt`. Uses **padded month/day** datetimes, **leap years** for February, and **end-of-day** (`23:59:59`) instead of an ambiguous midday cutoff. |
| **`extras/report.sh`** | Counts articles per Big-8–style top-level tree and total spool size; writes a timestamped CSV-style report. Ensures **`${REPORT_DIR:-/srv/www/htdocs/reports}/archive`** exists. Override install root: `REPORT_DIR=/path ./extras/report.sh`. |
| **`extras/biggestgroups.sh`** | Ranks directories by number of immediate child entries; produces Big-8–filtered and global top-50 / top-1000 lists, expire-header grep, and optional **`unwanted.log`** copy. Same **`REPORT_DIR`** convention as `report.sh`. |
| **`extras/Big-8_Report.sh`** | Smaller variant: Big-8 ranking only, written to **`$HOME`** (no web directory). |
| **`extras/crosspost_report.sh`** | Lists each article path with a **group count** derived from the **`Newsgroups:`** header (commas + 1). Sorts by that count descending; output **`$HOME/<timestamp>-sorted.csv`**. Uses **`mktemp`** instead of a fixed `/tmp` list. |

Historical notes about public report URLs live in **`extras/README.md`**.

---

## Layout

```
app/usenet_archiver.py   # NNTP → mbox client
extras/*.sh              # Tradspool reporting and archival helpers
LICENSE                  # BSD 2-Clause
```

---

## License

BSD 2-Clause — see **`LICENSE`**.
