### Usenet Archiver

Usenet Archiver is a tool designed to connect to Usenet servers, authenticate, fetch articles from a specified newsgroup, and save them to a local `.mbox` file. It offers a simple command-line interface for archiving Usenet newsgroups and supports both plaintext and SSL-encrypted connections.

This tool is **not** intended for downloading movies or other large files from binary newsgroups—it’s far too slow for that purpose. Instead, it’s built for creating archives of text-based newsgroups. Note that it’s relatively "dumb" in its approach: it treats spam as just another article to archive.

### Why?

The Usenet archives on the Internet Archive only extend to around 2013 and contain many significant gaps. By generating new archives, I aim to supplement the Internet Archive’s collection with more up-to-date data. Usenet Archiver is primarily a tool for archivists, historians, and data enthusiasts (or hoarders) like me.

### Notice

This tool should **only** be used with a paid Usenet subscription, not with free services like Eternal September or AIOE. If you get banned for misusing a Usenet provider, that’s on you. Paid Usenet providers can be found on [Reddit’s r/usenet](https://www.reddit.com/r/usenet/). A block account, offering substantial bandwidth, typically costs just a few dollars.

**Please don’t abuse free services!**

### Binary Version

The `bin/usenet_archiver.py` file is a Python script that should be able to run with minimal extra requirements. Previously, I had been experimenting with a go application but I know Python better.

### Basic usage:

```
usage: usenet_archiver.py [-h] --server SERVER [--port PORT] --username USERNAME --password PASSWORD --newsgroup NEWSGROUP [--ssl] [--verbose] [--timeout TIMEOUT]
                          [--start-date START_DATE] [--end-date END_DATE]

Fetch NNTP articles and save to mbox

options:
  -h, --help            show this help message and exit
  --server SERVER       NNTP server address
  --port PORT           NNTP server port
  --username USERNAME   Username for authentication
  --password PASSWORD   Password for authentication
  --newsgroup NEWSGROUP
                        Newsgroup to fetch articles from
  --ssl                 Use SSL connection
  --verbose             Enable verbose output
  --timeout TIMEOUT     Timeout for operations (seconds)
  --start-date START_DATE
                        Start date for articles (YYYY-MM-DD)
  --end-date END_DATE   End date for articles (YYYY-MM-DD)
```

### How to Run

Example:

```
/usr/bin/python3 usenet_archiver.py \
  --verbose \
  --server {{ myusenet_server}} \
  --port 563 
  --username {{ username }} \
  --password {{ password }} \
  --newsgroup news.groups \
  --ssl \
  --timeout 60 \
  --start-date 2021-01-01 \
  --end-date 2022-01-01
```

**Output**:
   - Articles are saved to a file like `news.groups.mbox`.
   - Logs are written to `news.groups.log` and `error_news.groups.log`.
   - When completed, the name of the mbox file is added to `completed_newsgroups.log`. If you run the script again, it will not overwrite what is in the existing `news.groups.mbox` unless you remove that entry from the completed log.

