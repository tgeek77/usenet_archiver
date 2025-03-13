### Usenet Archiver

Usenet Archiver is a tool designed to connect to Usenet servers, authenticate, fetch articles from a specified newsgroup, and save them to a local `.mbox` file. It offers a simple command-line interface for archiving Usenet newsgroups and supports both plaintext and SSL-encrypted connections.

This tool is **not** intended for downloading movies or other large files from binary newsgroups—it’s far too slow for that purpose. Instead, it’s built for creating archives of text-based newsgroups. Note that it’s relatively "dumb" in its approach: it treats spam as just another article to archive.

### Why?

The Usenet archives on the Internet Archive only extend to around 2013 and contain many significant gaps. By generating new archives, I aim to supplement the Internet Archive’s collection with more up-to-date data. Usenet Archiver is primarily a tool for archivists, historians, and data enthusiasts (or hoarders) like me.

### Notice

This tool should **only** be used with a paid Usenet subscription, not with free services like Eternal September or AIOE. If you get banned for misusing a Usenet provider, that’s on you. Paid Usenet providers can be found on [Reddit’s r/usenet](https://www.reddit.com/r/usenet/). A block account, offering substantial bandwidth, typically costs just a few dollars.

**Please don’t abuse free services!**

### Binary Version

The `bin/usenet_archiver` file is a precompiled binary for Linux x86_64. Since this is my first Go project, I’m keeping it simple for now. If you need it for a different OS or architecture, you’ll have to compile it yourself.

### How to Compile

1. **Prerequisites**:
   - Ensure you have Go installed (version 1.x or later).
   - Obtain access to a paid Usenet provider and note its address, port, and credentials.

2. **Compile the Program**:
   Clone the repository and compile the code:
   ```bash
   go build main.go
   ```

### How to Run

1. **Run the Program**:
   Execute the compiled binary with the required flags. Example:
   ```bash
   ./usenet_archiver -server "news.example.com" -port 563 -username "user" -password "pass" -newsgroup "alt.test" -ssl true -verbose true -timeout 60s
   ```
   - `-server`: The NNTP server address (required).
   - `-port`: The server port (default: 563 for SSL).
   - `-username` and `-password`: Credentials for authentication (required).
   - `-newsgroup`: The Usenet group to archive (e.g., `alt.test`, required).
   - `-ssl`: Use SSL (default: true).
   - `-verbose`: Enable detailed output (default: false).
   - `-timeout`: Set operation timeout (default: 60 seconds).

2. **Output**:
   - Articles are saved to a file like `alt_test.mbox`.
   - Logs are written to `fetch_log.txt`.

3. **Example Output**:
   Running the above command might create an `alt_test.mbox` file containing articles in mbox format and log connection details in `fetch_log.txt`.

### Future Updates

I plan to add a timeframe option in the future, allowing users to fetch archives within a specific date range. Ideally, I’d like to create yearly archives (e.g., January to January) of Usenet activity.