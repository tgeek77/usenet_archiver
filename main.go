package main

import (
    "bufio"
    "crypto/tls"
    "flag"
    "fmt"
    "log"
    "net"
    "os"
    "strings"
    "time"
)

// ... (Keep existing NNTPClient struct and methods unchanged until Article) ...

// New method to fetch headers using XOVER command
func (c *NNTPClient) GetHeaders(first, last int) (map[int]bool, error) {
    existingArticles := make(map[int]bool)
    err := c.send(fmt.Sprintf("XOVER %d-%d", first, last))
    if err != nil {
        return nil, err
    }
    
    resp, err := c.recv()
    if err != nil {
        return nil, err
    }
    if c.verbose {
        fmt.Printf("XOVER response: %s\n", resp)
    }
    if !strings.HasPrefix(resp, "224") {
        return nil, fmt.Errorf("XOVER failed: %s", resp)
    }

    reader := bufio.NewReader(c.conn)
    for {
        c.conn.SetReadDeadline(time.Now().Add(c.timeout))
        line, err := reader.ReadString('\n')
        if err != nil {
            return nil, err
        }
        line = strings.TrimSpace(line)
        if line == "." {
            break
        }
        parts := strings.Split(line, "\t")
        if len(parts) > 0 {
            var articleID int
            fmt.Sscanf(parts[0], "%d", &articleID)
            existingArticles[articleID] = true
        }
    }
    return existingArticles, nil
}

// Modified saveToMbox function
func saveToMbox(server string, port int, username, password, newsgroup string, useSSL, verbose bool, timeout time.Duration, startDate, endDate *time.Time) error {
    logFile, err := os.Create("fetch_log.txt")
    if err != nil {
        return err
    }
    defer logFile.Close()
    logger := log.New(logFile, "", log.LstdFlags)
    logger.Println("Starting save_to_mbox")

    client, err := NewNNTPClient(server, port, username, password, useSSL, verbose, timeout)
    if err != nil {
        return fmt.Errorf("failed to initialize client: %v", err)
    }
    defer client.Quit()
    logger.Println("NNTP client initialized")

    first, last, groupResp, err := client.Group(newsgroup)
    if err != nil {
        return fmt.Errorf("group error: %v", err)
    }
    logger.Printf("GROUP response: %s", groupResp)
    logger.Printf("First: %d, Last: %d, Range size: %d", first, last, last-first+1)

    // Get existing article headers
    existingArticles, err := client.GetHeaders(first, last)
    if err != nil {
        return fmt.Errorf("failed to fetch headers: %v", err)
    }
    logger.Printf("Found %d existing articles", len(existingArticles))

    mboxFileName := strings.ReplaceAll(newsgroup, ".", "_") + ".mbox"
    mboxFile, err := os.Create(mboxFileName)
    if err != nil {
        return err
    }
    defer mboxFile.Close()
    logger.Println("Opened mbox file")

    for articleID := last; articleID >= first; articleID-- {
        // Check if article exists
        if !existingArticles[articleID] {
            logger.Printf("Article %d does not exist, skipping", articleID)
            continue
        }

        // Fetch article content
        content, articleResp, err := client.Article(articleID)
        logger.Printf("ARTICLE %d response: %s", articleID, articleResp)
        if err != nil {
            logger.Printf("Article %d error: %v", articleID, err)
            fmt.Printf("Error fetching article %d: %v\n", articleID, err)
            // Attempt to reconnect
            logger.Println("Attempting to reconnect...")
            client.conn.Close()
            if err := client.connect(); err != nil {
                logger.Printf("Reconnect failed: %v", err)
                return fmt.Errorf("reconnect failed: %v", err)
            }
            logger.Println("Reconnected successfully")
            continue
        }

        if content != "" {
            // Parse article date from content (assuming Date: header exists)
            articleDate := time.Now() // Default to now if no date found
            for _, line := range strings.Split(content, "\n") {
                if strings.HasPrefix(line, "Date:") {
                    if parsedDate, err := time.Parse(time.RFC1123, strings.TrimPrefix(line, "Date:")); err == nil {
                        articleDate = parsedDate
                    }
                    break
                }
            }

            // Check date range if specified
            if startDate != nil && articleDate.Before(*startDate) {
                logger.Printf("Article %d before start date, skipping", articleID)
                continue
            }
            if endDate != nil && articleDate.After(*endDate) {
                logger.Printf("Article %d after end date, skipping", articleID)
                continue
            }

            logger.Printf("Article %d content fetched: %s...", content[:min(100, len(content))])
            timeStr := articleDate.UTC().Format("Mon, 02 Jan 2006 15:04:05 -0000")
            fmt.Fprintf(mboxFile, "From unknown %s\n%s\n\n", timeStr, content)
            mboxFile.Sync()
            logger.Printf("Article %d saved to mbox", articleID)
        } else {
            logger.Printf("Article %d not fetched: %s", articleID, articleResp)
        }
    }

    logger.Println("Finished save_to_mbox")
    return nil
}

func main() {
    server := flag.String("server", "", "NNTP server address")
    port := flag.Int("port", 563, "NNTP server port")
    username := flag.String("username", "", "Username for authentication")
    password := flag.String("password", "", "Password for authentication")
    newsgroup := flag.String("newsgroup", "", "Newsgroup to fetch articles from")
    useSSL := flag.Bool("ssl", true, "Use SSL connection")
    verbose := flag.Bool("verbose", false, "Enable verbose output")
    timeout := flag.Duration("timeout", 60*time.Second, "Timeout for operations")
    startDateStr := flag.String("start-date", "", "Start date (YYYY-MM-DD), optional")
    endDateStr := flag.String("end-date", "", "End date (YYYY-MM-DD), optional")
    flag.Parse()

    if *server == "" || *username == "" || *password == "" || *newsgroup == "" {
        log.Fatal("Server, username, password, and newsgroup must be specified")
    }

    var startDate, endDate *time.Time
    if *startDateStr != "" {
        if d, err := time.Parse("2006-01-02", *startDateStr); err == nil {
            startDate = &d
        } else {
            log.Fatalf("Invalid start date format: %v", err)
        }
    }
    if *endDateStr != "" {
        if d, err := time.Parse("2006-01-02", *endDateStr); err == nil {
            endDate = &d
        } else {
            log.Fatalf("Invalid end date format: %v", err)
        }
    }

    err := saveToMbox(*server, *port, *username, *password, *newsgroup, *useSSL, *verbose, *timeout, startDate, endDate)
    if err != nil {
        log.Printf("Top-level error: %v", err)
    }
}
