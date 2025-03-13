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

type NNTPClient struct {
	conn     net.Conn
	verbose  bool
	server   string
	port     int
	username string
	password string
	useSSL   bool
	timeout  time.Duration
}

func NewNNTPClient(server string, port int, username, password string, useSSL, verbose bool, timeout time.Duration) (*NNTPClient, error) {
	client := &NNTPClient{
		server:   server,
		port:     port,
		username: username,
		password: password,
		useSSL:   useSSL,
		verbose:  verbose,
		timeout:  timeout,
	}
	err := client.connect()
	if err != nil {
		return nil, err
	}
	return client, nil
}

func (c *NNTPClient) connect() error {
	addr := fmt.Sprintf("%s:%d", c.server, c.port)
	var conn net.Conn
	var err error

	if c.useSSL {
		conn, err = tls.Dial("tcp", addr, &tls.Config{})
	} else {
		conn, err = net.Dial("tcp", addr)
	}
	if err != nil {
		return err
	}
	c.conn = conn

	// Read welcome message
	welcome, err := c.recv()
	if err != nil {
		return fmt.Errorf("welcome message error: %v", err)
	}
	if c.verbose {
		fmt.Printf("Welcome: %s\n", welcome)
	}

	if c.username != "" && c.password != "" {
		err = c.send(fmt.Sprintf("AUTHINFO USER %s", c.username))
		if err != nil {
			return err
		}
		userResp, err := c.recv()
		if err != nil {
			return fmt.Errorf("user auth error: %v", err)
		}
		if c.verbose {
			fmt.Printf("USER response: %s\n", userResp)
		}

		err = c.send(fmt.Sprintf("AUTHINFO PASS %s", c.password))
		if err != nil {
			return err
		}
		authResp, err := c.recv()
		if err != nil {
			return fmt.Errorf("pass auth error: %v", err)
		}
		if c.verbose {
			fmt.Printf("PASS response: %s\n", authResp)
		}
		if !strings.HasPrefix(authResp, "281") {
			return fmt.Errorf("authentication failed: %s", authResp)
		}

		err = c.send("MODE READER")
		if err != nil {
			return err
		}
		modeResp, err := c.recv()
		if err != nil {
			return fmt.Errorf("mode reader error: %v", err)
		}
		if c.verbose {
			fmt.Printf("MODE response: %s\n", modeResp)
		}
	}
	return nil
}

func (c *NNTPClient) send(command string) error {
	c.conn.SetWriteDeadline(time.Now().Add(c.timeout))
	_, err := c.conn.Write([]byte(fmt.Sprintf("%s\r\n", command)))
	return err
}

func (c *NNTPClient) recv() (string, error) {
	c.conn.SetReadDeadline(time.Now().Add(c.timeout))
	reader := bufio.NewReader(c.conn)
	line, err := reader.ReadString('\n')
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(line), nil
}

func (c *NNTPClient) Group(newsgroup string) (int, int, string, error) {
	err := c.send(fmt.Sprintf("GROUP %s", newsgroup))
	if err != nil {
		return 0, 0, "", err
	}
	resp, err := c.recv()
	if err != nil {
		return 0, 0, "", err
	}
	if c.verbose {
		fmt.Printf("GROUP response: %s\n", resp)
	}
	if !strings.HasPrefix(resp, "211") {
		return 0, 0, "", fmt.Errorf("failed to select group %s: %s", newsgroup, resp)
	}

	parts := strings.Split(resp, " ")
	if len(parts) < 4 {
		return 0, 0, "", fmt.Errorf("invalid GROUP response: %s", resp)
	}

	var first, last int
	fmt.Sscanf(parts[2], "%d", &first)
	fmt.Sscanf(parts[3], "%d", &last)
	return first, last, resp, nil
}

func (c *NNTPClient) Stat(articleID int) (int, string, error) {
	err := c.send(fmt.Sprintf("STAT %d", articleID))
	if err != nil {
		return 0, "", err
	}
	resp, err := c.recv()
	if err != nil {
		return 0, "", err
	}
	if c.verbose {
		fmt.Printf("STAT %d response: %s\n", articleID, resp)
	}
	if strings.HasPrefix(resp, "223") {
		parts := strings.Split(resp, " ")
		if len(parts) < 2 {
			return 0, "", fmt.Errorf("invalid STAT response: %s", resp)
		}
		var id int
		fmt.Sscanf(parts[1], "%d", &id)
		return id, resp, nil
	}
	return 0, resp, nil
}

func (c *NNTPClient) Article(articleID int) (string, string, error) {
	err := c.send(fmt.Sprintf("ARTICLE %d", articleID))
	if err != nil {
		return "", "", err
	}
	resp, err := c.recv()
	if err != nil {
		return "", "", err
	}
	if c.verbose {
		fmt.Printf("ARTICLE %d response: %s\n", articleID, resp)
	}
	if !strings.HasPrefix(resp, "220") {
		return "", resp, nil
	}

	var content []string
	reader := bufio.NewReader(c.conn)
	for {
		c.conn.SetReadDeadline(time.Now().Add(c.timeout))
		line, err := reader.ReadString('\n')
		if err != nil {
			return "", "", err
		}
		line = strings.TrimSpace(line)
		if line == "." {
			break
		}
		content = append(content, line)
	}
	articleText := strings.Join(content, "\n")
	if c.verbose {
		fmt.Printf("Fetched content (first 100 chars): %s...\n", articleText[:min(100, len(articleText))])
	}
	return articleText, resp, nil
}

func (c *NNTPClient) Quit() error {
	err := c.send("QUIT")
	if err != nil {
		return err
	}
	_, err = c.recv()
	if err != nil {
		return err
	}
	return c.conn.Close()
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func saveToMbox(server string, port int, username, password, newsgroup string, useSSL, verbose bool, timeout time.Duration) error {
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

	validID, statResp, err := client.Stat(last)
	if err != nil {
		return fmt.Errorf("stat error: %v", err)
	}
	logger.Printf("STAT %d response: %s", last, statResp)
	if validID == 0 {
		logger.Printf("No valid article found at %d", last)
		return nil
	}

	mboxFileName := strings.ReplaceAll(newsgroup, ".", "_") + ".mbox"
	mboxFile, err := os.Create(mboxFileName)
	if err != nil {
		return err
	}
	defer mboxFile.Close()
	logger.Println("Opened mbox file")

	for articleID := validID; articleID >= first; articleID-- {
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
			logger.Printf("Article %d content fetched: %s...", content[:min(100, len(content))])
			timeStr := time.Now().UTC().Format("Mon, 02 Jan 2006 15:04:05 -0000")
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
	flag.Parse()

	if *server == "" || *username == "" || *password == "" || *newsgroup == "" {
		log.Fatal("Server, username, password, and newsgroup must be specified")
	}

	err := saveToMbox(*server, *port, *username, *password, *newsgroup, *useSSL, *verbose, *timeout)
	if err != nil {
		log.Printf("Top-level error: %v", err)
	}
}
