#!/usr/bin/python3

import socket
import ssl
import argparse
import logging
import time
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

class NNTPClient:
    def __init__(self, server, port, username, password, use_ssl, verbose, timeout):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.verbose = verbose
        self.timeout = timeout
        self.conn = None
        self.logger = logging.getLogger(__name__)
        if verbose:
            self.logger.setLevel(logging.DEBUG)

    def connect(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            if self.use_ssl:
                context = ssl.create_default_context()
                sock = context.wrap_socket(sock, server_hostname=self.server)
            sock.connect((self.server, self.port))
            self.conn = sock

            # Read welcome message
            welcome = self.recv()
            if self.verbose:
                print(f"Welcome: {welcome}")

            if self.username and self.password:
                self.send(f"AUTHINFO USER {self.username}")
                user_resp = self.recv()
                if self.verbose:
                    print(f"USER response: {user_resp}")

                self.send(f"AUTHINFO PASS {self.password}")
                auth_resp = self.recv()
                if self.verbose:
                    print(f"PASS response: {auth_resp}")
                if not auth_resp.startswith("281"):
                    raise Exception(f"Authentication failed: {auth_resp}")

                self.send("MODE READER")
                mode_resp = self.recv()
                if self.verbose:
                    print(f"MODE response: {mode_resp}")
        except Exception as e:
            if self.conn:
                self.conn.close()
            raise Exception(f"Connection error: {e}")

    def send(self, command):
        self.conn.settimeout(self.timeout)
        self.conn.sendall(f"{command}\r\n".encode("utf-8"))

    def recv(self):
        self.conn.settimeout(self.timeout)
        buffer = ""
        while True:
            try:
                data = self.conn.recv(8192).decode("utf-8", errors="ignore")
                if not data:
                    raise Exception("Connection closed by server")
                buffer += data
                if "\n" in buffer:
                    lines = buffer.split("\n", 1)
                    if len(lines) > 1:
                        buffer = lines[1]
                        return lines[0].strip()
            except socket.timeout:
                raise Exception("The read operation timed out")
        return buffer.strip()

    def recv_multiline(self):
        self.conn.settimeout(self.timeout)
        buffer = []
        while True:
            try:
                data = self.conn.recv(8192).decode("utf-8", errors="ignore")
                if not data:
                    raise Exception("Connection closed by server")
                lines = data.split("\n")
                for line in lines:
                    line = line.rstrip("\r")
                    if line == ".":
                        return buffer
                    buffer.append(line)
            except socket.timeout:
                raise Exception("The read operation timed out")

    def recv_article(self):
        self.conn.settimeout(self.timeout)
        buffer = []
        retries = 3
        while retries > 0:
            try:
                while True:
                    data = self.conn.recv(8192).decode("utf-8", errors="ignore")
                    if not data:
                        raise Exception("Connection closed by server")
                    lines = data.split("\n")
                    for line in lines:
                        line = line.rstrip("\r")
                        if line == ".":
                            return "\n".join(buffer)
                        buffer.append(line)
            except socket.timeout:
                retries -= 1
                if retries == 0:
                    raise Exception("The read operation timed out after retries")
                self.logger.warning(f"Timeout in recv_article, retries left: {retries}")
                time.sleep(1)  # Brief pause before retry
            except Exception as e:
                raise e

    def xhdr_date(self, start_id, end_id):
        self.send(f"XHDR DATE {start_id}-{end_id}")
        resp = self.recv()
        if self.verbose:
            print(f"XHDR DATE {start_id}-{end_id} response: {resp}")
        if not resp.startswith("221"):
            self.logger.warning(f"XHDR DATE not supported or failed: {resp}")
            return []
        lines = self.recv_multiline()
        result = []
        for line in lines:
            parts = line.split(" ", 1)
            if len(parts) == 2 and parts[0].isdigit():
                article_id, date_str = parts
                try:
                    date = parsedate_to_datetime(date_str.strip())
                    if date:
                        result.append((int(article_id), date))
                    else:
                        self.logger.warning(f"Invalid Date header for article {article_id}: {date_str}")
                except Exception as e:
                    self.logger.warning(f"Could not parse Date for article {article_id}: {date_str}, error: {e}")
        return result

    def group(self, newsgroup):
        self.send(f"GROUP {newsgroup}")
        resp = self.recv()
        if self.verbose:
            print(f"GROUP response: {resp}")
        if not resp.startswith("211"):
            raise Exception(f"Failed to select group {newsgroup}: {resp}")
        parts = resp.split()
        if len(parts) < 4:
            raise Exception(f"Invalid GROUP response: {resp}")
        first, last = int(parts[2]), int(parts[3])
        return first, last, resp

    def stat(self, article_id):
        self.send(f"STAT {article_id}")
        resp = self.recv()
        if self.verbose:
            print(f"STAT {article_id} response: {resp}")
        if resp.startswith("223"):
            parts = resp.split()
            if len(parts) < 2:
                raise Exception(f"Invalid STAT response: {resp}")
            return int(parts[1]), resp
        return 0, resp

    def article(self, article_id):
        self.send(f"ARTICLE {article_id}")
        resp = self.recv()
        if self.verbose:
            print(f"ARTICLE {article_id} response: {resp}")
        if not resp.startswith("220"):
            return "", resp
        content = self.recv_article()
        if self.verbose:
            print(f"Fetched article {article_id} (first 100 chars): {content[:100]}...")
        return content, resp

    def quit(self):
        try:
            self.send("QUIT")
            self.recv()
        finally:
            if self.conn:
                self.conn.close()

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Date must be in YYYY-MM-DD format")

def find_date_range(client, first, last, start_date, end_date):
    """Sample articles at coarse intervals to estimate ID range, refine with secondary sampling."""
    coarse_interval = 1000  # User-adjusted
    secondary_interval = 50  # User-adjusted
    buffer_size = 100  # Reduced buffer for granular sampling
    server_earliest_year = 2003  # Server retention starts at 2003
    # Dynamic min_reasonable_id based on start year
    min_reasonable_id = 100000 if start_date.year < 2010 else 400000
    client.logger.info(f"Starting coarse sampling with interval {coarse_interval}, min_reasonable_id={min_reasonable_id}")

    # Check if date range is entirely before server retention
    if start_date.year < server_earliest_year:
        client.logger.info(f"Date range {start_date.date()} to {end_date.date()} is before server retention ({server_earliest_year}), no articles available")
        return last + 1, first - 1, last + 1, first - 1  # Invalid range to trigger early exit

    # Coarse sampling
    sample_ids = range(first, last + 1, coarse_interval)
    date_samples = []
    for sample_id in sample_ids:
        try:
            dates = client.xhdr_date(sample_id, sample_id)
            if dates:
                article_id, date = dates[0]
                date_samples.append((article_id, date.date() if date else None))
                client.logger.info(f"Coarse sample at ID {article_id}: {date.date() if date else 'None'}")
        except Exception as e:
            client.logger.warning(f"Error in coarse sampling at ID {sample_id}: {e}")

    # Check if all samples are after end_date
    valid_samples = [date for _, date in date_samples if date]
    if valid_samples and all(date > end_date.date() for date in valid_samples):
        client.logger.info(f"All sampled dates are after {end_date.date()}, no articles in range {start_date.date()} to {end_date.date()}")
        return last + 1, first - 1, last + 1, first - 1  # Invalid range to trigger early exit

    # Find coarse range where dates are within or near start_date to end_date
    coarse_start_id = first
    coarse_end_id = last
    found_range = False
    for i in range(len(date_samples)):
        article_id, date = date_samples[i]
        if date is None:
            continue
        # Include samples within the range
        if start_date.date() <= date <= end_date.date():
            coarse_start_id = max(first, article_id - coarse_interval)
            coarse_end_id = min(last, article_id + coarse_interval)
            found_range = True
            break
        # If date is after end_date, check if previous sample is before start_date
        if i > 0 and date > end_date.date() and date_samples[i-1][1] and date_samples[i-1][1] < start_date.date():
            coarse_start_id = max(first, date_samples[i-1][0])
            coarse_end_id = min(last, article_id)
            found_range = True
            break
        # If date is before start_date, check if next sample is after end_date
        if i < len(date_samples) - 1 and date < start_date.date():
            next_date = date_samples[i+1][1]
            if next_date and next_date > end_date.date():
                coarse_start_id = max(first, article_id)
                coarse_end_id = min(last, date_samples[i+1][0])
                found_range = True
                break

    if not found_range:
        # Fallback to range with dates closest to target range
        min_date_diff = float('inf')
        closest_start_id = first
        closest_end_id = last
        for i in range(len(date_samples)):
            article_id, date = date_samples[i]
            if date is None:
                continue
            date_diff = abs((date - start_date.date()).days)
            if date_diff < min_date_diff:
                min_date_diff = date_diff
                closest_start_id = max(first, article_id - coarse_interval)
                closest_end_id = min(last, article_id + coarse_interval)
        coarse_start_id, coarse_end_id = closest_start_id, closest_end_id
        client.logger.warning(f"No samples within date range, using closest range: {coarse_start_id} to {coarse_end_id}")

    client.logger.info(f"Coarse range estimated: {coarse_start_id} to {coarse_end_id}")

    # Secondary sampling within coarse range
    client.logger.info(f"Starting secondary sampling with interval {secondary_interval} from {coarse_start_id} to {coarse_end_id}")
    secondary_samples = []
    for sample_id in range(coarse_start_id, coarse_end_id + 1, secondary_interval):
        try:
            dates = client.xhdr_date(sample_id, sample_id)
            if dates:
                article_id, date = dates[0]
                sample_date = date.date() if date else None
                secondary_samples.append((article_id, sample_date))
                client.logger.info(f"Secondary sample at ID {article_id}: {sample_date if sample_date else 'None'}")
                # Stop sampling if date is two years after end_date
                if sample_date and sample_date.year > end_date.year + 1:
                    coarse_end_id = min(coarse_end_id, article_id)
                    break
        except Exception as e:
            client.logger.warning(f"Error in secondary sampling at ID {sample_id}: {e}")

    # Refine start_id and end_id from secondary samples
    start_id = coarse_start_id
    end_id = coarse_end_id
    in_range_samples = [(article_id, date) for article_id, date in secondary_samples 
                       if date and start_date.date() <= date <= end_date.date()]
    if in_range_samples:
        start_id = min(article_id for article_id, _ in in_range_samples)
        end_id = max(article_id for article_id, _ in in_range_samples)
    else:
        # Use closest samples if none in range
        min_date_diff = float('inf')
        closest_id = coarse_start_id
        for article_id, date in secondary_samples:
            if date is None:
                continue
            date_diff = abs((date - start_date.date()).days)
            if date_diff < min_date_diff:
                min_date_diff = date_diff
                closest_id = article_id
        start_id = end_id = closest_id
        client.logger.warning(f"No secondary samples in date range, using closest ID: {closest_id}")

    # Store refined range for fallback
    refined_start_id = start_id
    refined_end_id = end_id

    # Add small buffer to ensure coverage
    start_id = max(first, start_id - buffer_size)
    end_id = min(last, end_id + buffer_size)

    # Validate range
    for check_id in [start_id, end_id]:
        try:
            sample_dates = client.xhdr_date(check_id, check_id)
            for article_id, date in sample_dates:
                sample_date = date.date() if date else None
                client.logger.info(f"Validation sample at ID {article_id}: {sample_date if sample_date else 'None'}")
            valid_samples = [date for _, date in sample_dates if date]
            if valid_samples and all(date.date() < start_date.date() or date.date() > end_date.date() for date in valid_samples):
                client.logger.warning(f"Validation sample at ID {check_id} outside date range {start_date.date()} to {end_date.date()}, range may be incorrect")
        except Exception as e:
            client.logger.warning(f"Error in validation at ID {check_id}: {e}")

    # Reject range if start_id is too low
    if start_id < min_reasonable_id:
        client.logger.warning(f"Start ID {start_id} rejected due to min_reasonable_id={min_reasonable_id}, using refined range {refined_start_id} to {refined_end_id}")
        start_id, end_id = refined_start_id, refined_end_id

    client.logger.info(f"Final estimated article ID range: {start_id} to {end_id}")
    return start_id, end_id, refined_start_id, refined_end_id

def save_to_mbox(server, port, username, password, newsgroup, use_ssl, verbose, timeout, start_date, end_date):
    # Construct log and mbox filenames based on newsgroup and date range
    if start_date and end_date:
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        log_filename = f"{newsgroup}-{start_str}-{end_str}.log"
        mbox_filename = f"{newsgroup}-{start_str}-{end_str}.mbox"
    else:
        log_filename = f"{newsgroup}.log"
        mbox_filename = f"{newsgroup}.mbox"
    
    # Check if mbox_filename is already in completed_newsgroups.log before setting up logging
    completed_log_path = "completed_newsgroups.log"
    try:
        if os.path.exists(completed_log_path):
            with open(completed_log_path, "r", encoding="utf-8") as completed_log:
                completed_mboxes = {line.strip() for line in completed_log if line.strip()}
            if mbox_filename in completed_mboxes:
                if verbose:
                    print(f"Newsgroup {newsgroup} already completed in {mbox_filename}, skipping")
                return
    except Exception as e:
        if verbose:
            print(f"Failed to read completed_newsgroups.log: {e}, proceeding with download")

    # Set up logging only if proceeding with download
    logging.basicConfig(filename=log_filename, level=logging.INFO, format="%(asctime)s %(message)s")
    logger = logging.getLogger(__name__)
    logger.info("Starting save_to_mbox")

    client = NNTPClient(server, port, username, password, use_ssl, verbose, timeout)
    invalid_date_count = 0  # Counter for missing/invalid Date headers
    try:
        client.connect()
        logger.info("NNTP client initialized")

        first, last, group_resp = client.group(newsgroup)
        logger.info(f"GROUP response: {group_resp}")
        logger.info(f"First: {first}, Last: {last}, Range size: {last - first + 1}")

        valid_id, stat_resp = client.stat(last)
        logger.info(f"STAT {last} response: {stat_resp}")
        if valid_id == 0:
            logger.info(f"No valid article found at {last}")
            return

        # Check if date range is entirely before server retention for date-based queries
        server_earliest_year = 2003
        if start_date and start_date.year < server_earliest_year:
            logger.info(f"Date range {start_date.date()} to {end_date.date()} is before server retention ({server_earliest_year}), exiting without creating mbox")
            return

        # Determine article ID range
        start_id, end_id = first, last
        refined_start_id, refined_end_id = first, last  # Initialize for fallback
        if start_date and end_date:
            try:
                start_id, end_id, refined_start_id, refined_end_id = find_date_range(client, first, last, start_date, end_date)
                logger.info(f"Range after find_date_range: {start_id} to {end_id}, refined: {refined_start_id} to {refined_end_id}")
                if start_id > end_id:
                    logger.info(f"No articles found in date range {start_date.date()} to {end_date.date()}, exiting without creating mbox")
                    return
                if start_id < first or end_id > last:
                    logger.warning(f"Invalid ID range from sampling ({start_id} to {end_id}), using refined range {refined_start_id} to {refined_end_id}")
                    start_id, end_id = refined_start_id, refined_end_id
            except Exception as e:
                logger.warning(f"Sampling failed: {e}, using refined range {refined_start_id} to {refined_end_id}")
                start_id, end_id = refined_start_id, refined_end_id
                if start_id > end_id:
                    logger.info(f"No articles found in date range {start_date.date()} to {end_date.date()}, exiting without creating mbox")
                    return
        else:
            logger.info(f"No date range specified, fetching all articles from ID {first} to {last}")
            # Use default min_reasonable_id for no-date queries
            min_reasonable_id = 400000
            if start_id < min_reasonable_id:
                logger.warning(f"Start ID {start_id} rejected due to min_reasonable_id={min_reasonable_id}, using {first} as fallback")
                start_id = first

        # Reject overly broad ranges for date-based queries only
        max_range_size = 10000
        if start_date and end_date and end_id - start_id > max_range_size:
            logger.warning(f"Range {start_id} to {end_id} too broad (> {max_range_size} IDs), using refined range {refined_start_id} to {refined_end_id}")
            start_id, end_id = refined_start_id, refined_end_id

        articles_processed = 0
        articles_saved = 0
        articles_skipped = 0
        mbox_file = None
        # Process from start_id to end_id
        # For no-date queries or when end_id is not after target range, process downward
        end_date_out_of_range = False
        if start_date and end_date:
            try:
                sample_dates = client.xhdr_date(end_id, end_id)
                end_date_out_of_range = any(date and date.date().year > end_date.year for _, date in sample_dates)
            except Exception as e:
                logger.warning(f"Error checking end_id {end_id}: {e}, assuming out of range")
                end_date_out_of_range = True

        if end_date_out_of_range:
            logger.info(f"End ID {end_id} is after target range (>{end_date.date() if start_date else 'no date'}), processing from {start_id} upward")
            article_range = range(start_id, end_id + 1)
        else:
            logger.info(f"Processing from {end_id} downward to {start_id}")
            article_range = range(end_id, start_id - 1, -1)

        for article_id in article_range:
            retries = 3
            while retries > 0:
                try:
                    content, article_resp = client.article(article_id)
                    logger.info(f"ARTICLE {article_id} response: {article_resp}")
                    articles_processed += 1
                    if not content:
                        logger.info(f"Article {article_id} not fetched: {article_resp}")
                        articles_skipped += 1
                        break

                    # Check article date for date-based queries
                    date_valid = True
                    article_date = None
                    if start_date and end_date:
                        date_line = next((line for line in content.split("\n") if line.lower().startswith("date:")), None)
                        if not date_line:
                            logger.warning(f"Article {article_id} has no Date header, including with warning")
                            invalid_date_count += 1
                            date_valid = False
                            article_date = None
                        else:
                            try:
                                article_date = parsedate_to_datetime(date_line[5:].strip())
                                if not article_date:
                                    logger.warning(f"Article {article_id} has invalid Date header: {date_line[5:].strip()}, including with warning")
                                    invalid_date_count += 1
                                    date_valid = False
                                else:
                                    logger.info(f"Article {article_id} Date: {article_date.date()}")
                                    date_valid = True
                            except Exception as e:
                                logger.warning(f"Could not parse Date for article {article_id}: {date_line[5:].strip()}, error: {e}, including with warning")
                                invalid_date_count += 1
                                date_valid = False
                                article_date = None

                    # Early termination for date-based queries
                    if start_date and end_date:
                        if not end_date_out_of_range and date_valid and article_date.date() < start_date.date():
                            logger.info(f"Article {article_id} before start date {start_date.date()}, stopping")
                            logger.info(f"Processed {articles_processed} articles, saved {articles_saved}, skipped {articles_skipped}, invalid/missing Date headers: {invalid_date_count}")
                            if articles_saved == 0 and mbox_file is None:
                                logger.info("No articles saved, no mbox file created")
                            return
                        if end_date_out_of_range and date_valid and article_date.date() > end_date.date():
                            logger.info(f"Article {article_id} after end date {end_date.date()}, stopping")
                            logger.info(f"Processed {articles_processed} articles, saved {articles_saved}, skipped {articles_skipped}, invalid/missing Date headers: {invalid_date_count}")
                            if articles_saved == 0 and mbox_file is None:
                                logger.info("No articles saved, no mbox file created")
                            return

                    # Include article if no date range or if date is valid/in range or invalid
                    if not (start_date and end_date) or not date_valid or (date_valid and start_date and end_date and
                                                                          start_date.date() <= article_date.date() <= end_date.date()):
                        logger.info(f"Article {article_id} content fetched: {content[:100]}...")
                        try:
                            # Create mbox file only when first article is saved
                            if mbox_file is None:
                                mbox_file = open(mbox_filename, "w", encoding="utf-8")
                                logger.info(f"Opened mbox file: {mbox_filename}")
                            
                            # Extract From: header for mbox From_ line
                            from_line = next((line for line in content.split("\n") if line.lower().startswith("from:")), None)
                            sender = "unknown"
                            if from_line:
                                sender_part = from_line[5:].strip()
                                # Use email address or name, removing quotes or angle brackets
                                sender = sender_part.split("<")[-1].replace(">", "").strip() or sender_part.strip()
                                if not sender or len(sender) > 100:  # Fallback if invalid or too long
                                    sender = "unknown"
                            
                            # Escape 'From ' lines in the article body
                            escaped_content = []
                            for line in content.split("\n"):
                                if line.startswith("From "):
                                    escaped_content.append(f">{line}")
                                else:
                                    escaped_content.append(line)
                            escaped_content = "\n".join(escaped_content)

                            # Write mbox From_ line and article
                            time_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
                            mbox_file.write(f"From {sender} {time_str}\n{escaped_content}\n\n")
                            mbox_file.flush()
                            logger.info(f"Article {article_id} saved to mbox with sender: {sender}")
                            articles_saved += 1
                        except Exception as e:
                            logger.error(f"Failed to write article {article_id} to mbox: {e}")
                            raise Exception(f"Failed to write to mbox: {e}")
                    else:
                        logger.info(f"Article {article_id} outside date range {start_date.date()} to {end_date.date()}, skipping")
                        articles_skipped += 1
                    break  # Success, move to next article
                except Exception as e:
                    retries -= 1
                    logger.error(f"Error fetching article {article_id}: {e}, retries left: {retries}")
                    print(f"Error fetching article {article_id}: {e}")
                    if retries == 0:
                        logger.error(f"Max retries reached for article {article_id}, skipping")
                        articles_skipped += 1
                        break
                    # Attempt to reconnect
                    logger.info("Attempting to reconnect...")
                    try:
                        client.quit()
                        client.connect()
                        client.group(newsgroup)  # Re-select newsgroup
                        logger.info("Reconnected successfully and re-selected newsgroup")
                    except Exception as reconnect_err:
                        logger.error(f"Reconnect failed: {reconnect_err}")
                        raise Exception(f"Reconnect failed: {reconnect_err}")
        logger.info(f"Processed {articles_processed} articles, saved {articles_saved}, skipped {articles_skipped}, invalid/missing Date headers: {invalid_date_count}")
        if articles_saved == 0 and mbox_file is None:
            logger.info("No articles saved, no mbox file created")
        elif articles_saved > 0:
            # Log completed mbox filename to completed_newsgroups.log
            try:
                with open("completed_newsgroups.log", "a", encoding="utf-8") as completed_log:
                    completed_log.write(f"{mbox_filename}\n")
                    completed_log.flush()
                logger.info(f"Logged completed mbox to completed_newsgroups.log: {mbox_filename}")
            except Exception as e:
                logger.error(f"Failed to log completed mbox to completed_newsgroups.log: {e}")
    except Exception as e:
        logger.error(f"Critical error in save_to_mbox: {e}")
        raise
    finally:
        if 'mbox_file' in locals() and mbox_file is not None:
            mbox_file.close()
        if 'client' in locals():
            client.quit()
    logger.info("Finished save_to_mbox")

def main():
    parser = argparse.ArgumentParser(description="Fetch NNTP articles and save to mbox")
    parser.add_argument("--server", required=True, help="NNTP server address")
    parser.add_argument("--port", type=int, default=563, help="NNTP server port")
    parser.add_argument("--username", required=True, help="Username for authentication")
    parser.add_argument("--password", required=True, help="Password for authentication")
    parser.add_argument("--newsgroup", required=True, help="Newsgroup to fetch articles from")
    parser.add_argument("--ssl", action="store_true", default=True, help="Use SSL connection")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout for operations (seconds)")
    parser.add_argument("--start-date", help="Start date for articles (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date for articles (YYYY-MM-DD)")
    args = parser.parse_args()

    start_date = parse_date(args.start_date) if args.start_date else None
    end_date = parse_date(args.end_date) if args.end_date else None

    save_to_mbox(
        args.server,
        args.port,
        args.username,
        args.password,
        args.newsgroup,
        args.ssl,
        args.verbose,
        args.timeout,
        start_date,
        end_date
    )

if __name__ == "__main__":
    main()
