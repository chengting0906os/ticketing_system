//go:build concurrent || standalone
// +build concurrent standalone

// Concurrent Load Test for Ticketing System
// Build with: go build -tags concurrent
// Or: go build concurrent_loadtest.go types.go

package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"runtime/pprof"
	"runtime/trace"
	"sort"
	"sync"
	"sync/atomic"
	"time"
)

// API Request/Response Types (shared types are in types.go)
type CreateUserRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name"`
	Role     string `json:"role"`
}

// Metrics Collection
type Metrics struct {
	totalRequests    int64
	successCount     int64
	failureCount     int64
	pendingCount     int64
	bookedSeatsCount int64 // Track total booked seats
	latencies        []time.Duration
	latenciesMutex   sync.Mutex
	bookedSeats      map[string]bool
	bookedSeatsMutex sync.RWMutex
	duplicateSeats   int64
	startTime        time.Time
	endTime          time.Time
	firstSendTime    atomic.Value // time.Time
	lastSendTime     atomic.Value // time.Time
}

// Configuration
type Config struct {
	Host             string
	TotalRequests    int
	Concurrency      int
	ClientPoolSize   int // Number of HTTP clients in pool
	EventID          int
	TotalSeats       int // Total seats available for the event
	Sections         []string
	Subsections      []int
	Mode             string // "best_available" or "mixed"
	BestAvailableQty int
	Debug            bool // Enable debug output
}

func mustParseURL(urlStr string) *url.URL {
	u, err := url.Parse(urlStr)
	if err != nil {
		panic(err)
	}
	return u
}

func main() {
	// Parse command line flags
	config := Config{}
	flag.StringVar(&config.Host, "host", "", "API host (overrides API_HOST env var)")
	flag.IntVar(&config.TotalRequests, "requests", 50000, "Total number of requests")
	flag.IntVar(&config.Concurrency, "concurrency", 500, "Number of concurrent workers")
	flag.IntVar(&config.ClientPoolSize, "clients", 10, "Number of HTTP clients in pool")
	flag.IntVar(&config.EventID, "event", 1, "Event ID to book")
	flag.IntVar(&config.TotalSeats, "total-seats", 500, "Total seats available (500/5000/50000)")
	flag.StringVar(&config.Mode, "mode", "best_available", "Booking mode: best_available or mixed")
	flag.IntVar(&config.BestAvailableQty, "quantity", 2, "Number of seats per booking for best_available mode")
	flag.BoolVar(&config.Debug, "debug", false, "Enable debug output (verbose logging)")

	// Profiling flags
	var cpuProfile string
	var memProfile string
	var blockProfile string
	var mutexProfile string
	var traceProfile string

	flag.StringVar(&cpuProfile, "cpuprofile", "", "Write CPU profile to file")
	flag.StringVar(&memProfile, "memprofile", "", "Write memory profile to file")
	flag.StringVar(&blockProfile, "blockprofile", "", "Write block profile to file")
	flag.StringVar(&mutexProfile, "mutexprofile", "", "Write mutex profile to file")
	flag.StringVar(&traceProfile, "trace", "", "Write execution trace to file")

	flag.Parse()

	// Use API_HOST env var if -host flag not provided
	if config.Host == "" {
		config.Host = os.Getenv("API_HOST")
		if config.Host == "" {
			config.Host = "http://localhost" // fallback default
		}
	}

	// Enable profiling if requested
	if blockProfile != "" {
		runtime.SetBlockProfileRate(1)
	}
	if mutexProfile != "" {
		runtime.SetMutexProfileFraction(1)
	}

	// Start CPU profiling
	if cpuProfile != "" {
		f, err := os.Create(cpuProfile)
		if err != nil {
			fmt.Printf("❌ Could not create CPU profile: %v\n", err)
			os.Exit(1)
		}
		defer f.Close()
		if err := pprof.StartCPUProfile(f); err != nil {
			fmt.Printf("❌ Could not start CPU profile: %v\n", err)
			os.Exit(1)
		}
		defer pprof.StopCPUProfile()
		fmt.Printf("🔍 CPU profiling enabled: %s\n", cpuProfile)
	}

	// Start execution trace
	if traceProfile != "" {
		f, err := os.Create(traceProfile)
		if err != nil {
			fmt.Printf("❌ Could not create trace file: %v\n", err)
			os.Exit(1)
		}
		defer f.Close()
		if err := trace.Start(f); err != nil {
			fmt.Printf("❌ Could not start trace: %v\n", err)
			os.Exit(1)
		}
		defer trace.Stop()
		fmt.Printf("🔍 Execution trace enabled: %s\n", traceProfile)
	}

	// Default sections and subsections (match actual database seeded data)
	config.Sections = []string{"A", "B", "C", "D", "E", "F", "G", "H", "I", "J"} // 10 sections
	config.Subsections = []int{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}                    // Each section has 10 subsections

	// Auto-detect total seats from DEPLOY_ENV if not explicitly set
	if config.TotalSeats == 500 { // Default value, check if user didn't override
		deployEnv := os.Getenv("DEPLOY_ENV")
		switch deployEnv {
		case "local_dev":
			config.TotalSeats = 500 // 10 sections × 10 subsections × 1 row × 5 seats
		case "development":
			config.TotalSeats = 500 // 10 sections × 10 subsections × 1 row × 5 seats (same as local_dev)
		case "staging":
			config.TotalSeats = 5000 // 10 sections × 10 subsections × 12 rows × 21 seats (approx)
		case "production":
			config.TotalSeats = 50000 // 10 sections × 10 subsections × 25 rows × 20 seats
		default:
			config.TotalSeats = 500 // Default to local_dev
		}
	}

	fmt.Println("========================================")
	fmt.Println("🎫 Ticketing System Load Test")
	fmt.Println("========================================")
	fmt.Printf("Host:        %s\n", config.Host)
	fmt.Printf("Requests:    %d\n", config.TotalRequests)
	fmt.Printf("Concurrency: %d\n", config.Concurrency)
	fmt.Printf("Event ID:    %d\n", config.EventID)
	fmt.Printf("Total Seats: %d\n", config.TotalSeats)
	fmt.Printf("Mode:        %s\n", config.Mode)
	fmt.Printf("Quantity:    1 seat/booking (fixed)\n")
	fmt.Println("========================================")

	// Initialize metrics
	metrics := &Metrics{
		latencies:   make([]time.Duration, 0, config.TotalRequests),
		bookedSeats: make(map[string]bool),
		startTime:   time.Now(),
	}

	// Create worker pool
	requestChan := make(chan int, config.TotalRequests)
	var wg sync.WaitGroup

	// Pre-create authenticated HTTP client pool
	// Phase 1: Authenticate once and create client pool (warm-up phase)
	fmt.Println("\n📝 Phase 1: Creating HTTP client pool...")
	fmt.Printf("   (Creating %d clients with shared authentication)\n", config.ClientPoolSize)
	fmt.Println("   (Login phase - NOT included in performance metrics)")
	setupStartTime := time.Now()

	// Login once and get authenticated cookies
	masterClient, err := createAuthenticatedClient(config.Host, 0)
	if err != nil {
		fmt.Printf("❌ Failed to authenticate: %v\n", err)
		return
	}

	// Extract cookies from authenticated client
	masterCookies := masterClient.Jar.Cookies(mustParseURL(config.Host))

	// Create pool of HTTP clients, all sharing the same cookies
	clientPool := make([]*http.Client, config.ClientPoolSize)
	for i := 0; i < config.ClientPoolSize; i++ {
		jar, _ := cookiejar.New(nil)
		jar.SetCookies(mustParseURL(config.Host), masterCookies)

		transport := &http.Transport{
			MaxIdleConns:        1000,
			MaxIdleConnsPerHost: 1000,
			MaxConnsPerHost:     0,
			IdleConnTimeout:     90 * time.Second,
		}

		clientPool[i] = &http.Client{
			Jar:       jar,
			Timeout:   600 * time.Second,
			Transport: transport,
		}
	}

	setupDuration := time.Since(setupStartTime)
	fmt.Printf("   ✅ %d clients authenticated in %.2fs\n", config.ClientPoolSize, setupDuration.Seconds())
	fmt.Printf("   ℹ️  %d workers will round-robin across %d clients\n", config.Concurrency, config.ClientPoolSize)

	// Phase 2: Start load test (only booking requests)
	fmt.Println("\n🚀 Phase 2: Starting booking load test...")
	fmt.Println("   (Performance measurement starts NOW)")
	testStartTime := time.Now()

	// Create separate WaitGroup for tracking responses
	var responseWg sync.WaitGroup

	// Start workers - each worker picks a client from pool (round-robin)
	for i := 0; i < config.Concurrency; i++ {
		wg.Add(1)
		workerID := i
		clientIdx := i % len(clientPool) // Round-robin assignment
		go worker(workerID, clientPool[clientIdx], requestChan, &config, metrics, &wg, &responseWg)
	}

	// Send requests
	for i := 0; i < config.TotalRequests; i++ {
		requestChan <- i
	}
	close(requestChan)

	// Wait for all workers to finish sending requests
	wg.Wait()
	fmt.Println("\n   ✅ All requests sent! Waiting for responses...")

	// Wait for all responses to be received
	responseWg.Wait()
	metrics.endTime = time.Now()

	// Print newline after progress bar to separate from results
	fmt.Println()

	// Print results
	printResults(metrics, config, testStartTime)

	// Write memory profile if requested
	if memProfile != "" {
		f, err := os.Create(memProfile)
		if err != nil {
			fmt.Printf("❌ Could not create memory profile: %v\n", err)
		} else {
			runtime.GC() // Get up-to-date statistics
			if err := pprof.WriteHeapProfile(f); err != nil {
				fmt.Printf("❌ Could not write memory profile: %v\n", err)
			} else {
				fmt.Printf("📊 Memory profile written to: %s\n", memProfile)
			}
			f.Close()
		}
	}

	// Write block profile if requested
	if blockProfile != "" {
		f, err := os.Create(blockProfile)
		if err != nil {
			fmt.Printf("❌ Could not create block profile: %v\n", err)
		} else {
			if err := pprof.Lookup("block").WriteTo(f, 0); err != nil {
				fmt.Printf("❌ Could not write block profile: %v\n", err)
			} else {
				fmt.Printf("📊 Block profile written to: %s\n", blockProfile)
			}
			f.Close()
		}
	}

	// Write mutex profile if requested
	if mutexProfile != "" {
		f, err := os.Create(mutexProfile)
		if err != nil {
			fmt.Printf("❌ Could not create mutex profile: %v\n", err)
		} else {
			if err := pprof.Lookup("mutex").WriteTo(f, 0); err != nil {
				fmt.Printf("❌ Could not write mutex profile: %v\n", err)
			} else {
				fmt.Printf("📊 Mutex profile written to: %s\n", mutexProfile)
			}
			f.Close()
		}
	}
}

func createAuthenticatedClient(host string, workerID int) (*http.Client, error) {
	// Create client with cookie jar
	jar, err := cookiejar.New(nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create cookie jar: %w", err)
	}

	// Configure HTTP transport with larger connection pool
	transport := &http.Transport{
		MaxIdleConns:        1000,             // Total idle connections across all hosts
		MaxIdleConnsPerHost: 1000,             // Idle connections per host (support high concurrency)
		MaxConnsPerHost:     0,                // 0 = unlimited active connections
		IdleConnTimeout:     90 * time.Second, // Keep connections alive for reuse
	}

	client := &http.Client{
		Jar:       jar,
		Timeout:   60 * time.Second,
		Transport: transport,
	}

	// Generate unique user credentials (must be pre-registered)
	// Match seed_data.py format: b_1@t.com to b_10@t.com (workerID 0-9 maps to user 1-10)
	email := fmt.Sprintf("b_%d@t.com", workerID+1)
	password := "P@ssw0rd" // Fixed password for all users (set by seed_data.py)

	// Login to get JWT token (user must already exist)
	err = loginUser(client, host, email, password)
	if err != nil {
		return nil, fmt.Errorf("login failed for %s: %w\nHint: Run 'make seed' or 'make docker-seed' to setup test data first", email, err)
	}

	return client, nil
}

func loginUser(client *http.Client, host, email, password string) error {
	reqBody := LoginRequest{
		Email:    email,
		Password: password,
	}

	body, _ := json.Marshal(reqBody)
	resp, err := client.Post(host+"/api/user/login", "application/json", bytes.NewBuffer(body))
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	// Debug: Check cookies after login
	if client.Jar != nil {
		parsedURL, _ := resp.Request.URL.Parse("/")
		cookies := client.Jar.Cookies(parsedURL)
		if len(cookies) == 0 {
			return fmt.Errorf("no cookies received after login for %s", email)
		}
	}

	return nil
}

func worker(id int, client *http.Client, requests <-chan int, config *Config, metrics *Metrics, wg *sync.WaitGroup, responseWg *sync.WaitGroup) {
	defer wg.Done()

	for reqNum := range requests {
		// Increment and show progress BEFORE sending request (same line update)
		sent := atomic.AddInt64(&metrics.totalRequests, 1)

		// Debug: Show when request is actually sent
		if config.Debug {
			fmt.Printf("\r   [Worker %d] Sending request #%d at %s", id, sent, time.Now().Format("15:04:05.000"))
		} else {
			fmt.Printf("\r   Sending: %d/%d requests", sent, config.TotalRequests)
		}

		// Create booking request
		bookingReq := generateBookingRequest(reqNum, config, metrics)

		// Launch goroutine to handle request/response asynchronously
		responseWg.Add(1)
		go func(reqID int64, req BookingCreateRequest) {
			defer responseWg.Done()

			// Send request and measure latency
			start := time.Now()
			success, seats := sendBookingRequestWithTiming(client, config.Host, req, metrics)
			latency := time.Since(start)

			// Debug: Show when response is received
			if config.Debug {
				fmt.Printf("\r   [Worker %d] Response #%d received after %.2fs\n", id, reqID, latency.Seconds())
			}

			// Update success/failure metrics
			if success {
				atomic.AddInt64(&metrics.successCount, 1)

				// Track booked seats for duplicate detection and count
				if len(seats) > 0 {
					metrics.bookedSeatsMutex.Lock()
					for _, seat := range seats {
						if metrics.bookedSeats[seat] {
							atomic.AddInt64(&metrics.duplicateSeats, 1)
						}
						metrics.bookedSeats[seat] = true
					}
					metrics.bookedSeatsMutex.Unlock()

					// Update booked seats count
					atomic.AddInt64(&metrics.bookedSeatsCount, int64(len(seats)))
				} else {
					atomic.AddInt64(&metrics.pendingCount, 1)
				}
			} else {
				atomic.AddInt64(&metrics.failureCount, 1)
			}

			// Record latency
			metrics.latenciesMutex.Lock()
			metrics.latencies = append(metrics.latencies, latency)
			metrics.latenciesMutex.Unlock()
		}(sent, bookingReq)
	}
}

func generateBookingRequest(reqNum int, config *Config, metrics *Metrics) BookingCreateRequest {
	// Go 1.20+: rand is automatically seeded, no need to call rand.Seed()
	section := config.Sections[rand.Intn(len(config.Sections))]
	subsection := config.Subsections[rand.Intn(len(config.Subsections))]

	// Fixed quantity: always buy 1 ticket per request
	quantity := 1

	req := BookingCreateRequest{
		EventID:           config.EventID,
		Section:           section,
		Subsection:        subsection,
		SeatSelectionMode: "best_available",
		SeatPositions:     []string{}, // Initialize as empty slice to serialize as [] not null
		Quantity:          quantity,
	}

	// Mixed mode: 20% manual selection, 80% best available
	if config.Mode == "mixed" && rand.Float32() < 0.2 {
		req.SeatSelectionMode = "manual"
		req.SeatPositions = []string{
			fmt.Sprintf("%s-%d-%d-%d", section, subsection, rand.Intn(10)+1, rand.Intn(20)+1),
		}
		req.Quantity = 0
	}

	return req
}

func sendBookingRequestWithTiming(client *http.Client, host string, req BookingCreateRequest, metrics *Metrics) (bool, []string) {
	const maxRetries = 20
	const baseDelay = 100 * time.Millisecond // 0.1 second

	var lastStatusCode int
	var lastBody []byte

	for attempt := 0; attempt < maxRetries; attempt++ {
		// Linear backoff: 0.1s, 0.2s, 0.3s, 0.4s, 0.5s, etc.
		if attempt > 0 {
			backoff := baseDelay * time.Duration(attempt)
			time.Sleep(backoff)
		}

		body, _ := json.Marshal(req)

		// Debug: Check cookies before sending booking request
		bookingURL := host + "/api/booking"
		httpReq, _ := http.NewRequest("POST", bookingURL, bytes.NewBuffer(body))
		httpReq.Header.Set("Content-Type", "application/json")

		if client.Jar != nil {
			cookies := client.Jar.Cookies(httpReq.URL)
			if len(cookies) == 0 {
				fmt.Printf("⚠️  No cookies found for booking request to %s\n", bookingURL)
			} else {
				// Manually add cookies to request for debugging
				for _, cookie := range cookies {
					httpReq.AddCookie(cookie)
				}
			}
		}

		// Record timing JUST before actual HTTP send (only on first attempt)
		if attempt == 0 {
			sendTime := time.Now()
			if metrics.firstSendTime.Load() == nil {
				metrics.firstSendTime.Store(sendTime)
			}
			metrics.lastSendTime.Store(sendTime)
		}

		resp, err := client.Do(httpReq)
		if err != nil {
			if attempt < maxRetries-1 {
				fmt.Printf("⚠️  Attempt %d/%d failed with error: %v, retrying...\n", attempt+1, maxRetries, err)
				continue
			}
			fmt.Printf("❌ Request error after %d attempts: %v\n", maxRetries, err)
			return false, nil
		}

		bodyBytes, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		lastStatusCode = resp.StatusCode
		lastBody = bodyBytes

		// Success cases - don't retry
		if resp.StatusCode == http.StatusCreated {
			var bookingResp BookingResponse
			if err := json.Unmarshal(bodyBytes, &bookingResp); err == nil {
				// API doesn't return seat_ids in creation response
				return true, nil
			}
			return true, nil
		}

		if resp.StatusCode == http.StatusAccepted || resp.StatusCode == http.StatusOK {
			return true, nil
		}

		// Client errors (4xx) - don't retry except 429 (rate limit)
		if resp.StatusCode >= 400 && resp.StatusCode < 500 && resp.StatusCode != http.StatusTooManyRequests {
			fmt.Printf("⚠️  Client error %d: %s (not retrying)\n", resp.StatusCode, string(bodyBytes))
			return false, nil
		}

		// Server errors (5xx) or rate limit (429) - retry
		if attempt < maxRetries-1 {
			fmt.Printf("⚠️  Attempt %d/%d failed with status %d, retrying...\n", attempt+1, maxRetries, resp.StatusCode)
			continue
		}
	}

	// All retries exhausted
	fmt.Printf("❌ Request failed after %d attempts. Last status: %d, body: %s\n", maxRetries, lastStatusCode, string(lastBody))
	return false, nil
}

func printResults(metrics *Metrics, config Config, testStartTime time.Time) {
	duration := metrics.endTime.Sub(testStartTime)
	totalRequests := atomic.LoadInt64(&metrics.totalRequests)
	successCount := atomic.LoadInt64(&metrics.successCount)
	failureCount := atomic.LoadInt64(&metrics.failureCount)
	pendingCount := atomic.LoadInt64(&metrics.pendingCount)
	duplicateSeats := atomic.LoadInt64(&metrics.duplicateSeats)

	// Get CPU info
	numCPU := runtime.NumCPU()
	numGoroutines := runtime.NumGoroutine()

	var memStats runtime.MemStats
	runtime.ReadMemStats(&memStats)

	fmt.Println("\n========================================")
	fmt.Println("📊 Load Test Results")
	fmt.Println("========================================")

	// Show request sending speed
	var firstTime, lastTime time.Time
	var sendDuration time.Duration
	var hasSendTiming bool
	if metrics.firstSendTime.Load() != nil && metrics.lastSendTime.Load() != nil {
		firstTime = metrics.firstSendTime.Load().(time.Time)
		lastTime = metrics.lastSendTime.Load().(time.Time)
		sendDuration = lastTime.Sub(firstTime)
		hasSendTiming = true
		fmt.Println("🚀 Request Sending Speed:")
		fmt.Printf("  First request sent at:  %s\n", firstTime.Format("15:04:05.000"))
		fmt.Printf("  Last request sent at:   %s\n", lastTime.Format("15:04:05.000"))
		fmt.Printf("  All %d requests sent in: %.3fms\n", totalRequests, sendDuration.Seconds()*1000)
		fmt.Printf("  Sending rate:           %.0f req/ms\n", float64(totalRequests)/sendDuration.Seconds()/1000)
		fmt.Println()
	}

	fmt.Println("⏱️  Test Duration:")
	fmt.Printf("  Pure booking time:  %.2fs\n", duration.Seconds())
	fmt.Printf("  (Auth setup time excluded from metrics)\n")
	fmt.Println()
	fmt.Println("📈 Request Statistics:")
	fmt.Printf("  Total Requests:     %d\n", totalRequests)
	fmt.Printf("  Successful:         %d (%.2f%%)\n", successCount, float64(successCount)/float64(totalRequests)*100)
	fmt.Printf("  Failed:             %d (%.2f%%)\n", failureCount, float64(failureCount)/float64(totalRequests)*100)
	fmt.Printf("  Pending:            %d (bookings without immediate seat IDs)\n", pendingCount)
	fmt.Printf("  Throughput:         %.2f req/s\n", float64(totalRequests)/duration.Seconds())

	fmt.Println("\n🪑 Seat Booking Stats:")
	metrics.bookedSeatsMutex.RLock()
	totalSeats := len(metrics.bookedSeats)
	metrics.bookedSeatsMutex.RUnlock()
	fmt.Printf("Unique Seats:       %d\n", totalSeats)
	fmt.Printf("Duplicate Seats:    %d\n", duplicateSeats)
	if duplicateSeats > 0 {
		fmt.Println("⚠️  WARNING: Duplicate seat reservations detected!")
	} else {
		fmt.Println("✅ No duplicate seat reservations")
	}

	// Calculate latency percentiles
	fmt.Println("\n⏱️  Latency Distribution:")
	var min, max, avg, p50, p75, p90, p95, p99 time.Duration
	if len(metrics.latencies) > 0 {
		sort.Slice(metrics.latencies, func(i, j int) bool {
			return metrics.latencies[i] < metrics.latencies[j]
		})

		p50 = metrics.latencies[len(metrics.latencies)*50/100]
		p75 = metrics.latencies[len(metrics.latencies)*75/100]
		p90 = metrics.latencies[len(metrics.latencies)*90/100]
		p95 = metrics.latencies[len(metrics.latencies)*95/100]
		p99 = metrics.latencies[len(metrics.latencies)*99/100]
		min = metrics.latencies[0]
		max = metrics.latencies[len(metrics.latencies)-1]

		// Calculate average
		var sum time.Duration
		for _, lat := range metrics.latencies {
			sum += lat
		}
		avg = sum / time.Duration(len(metrics.latencies))

		fmt.Printf("Min:    %v\n", min)
		fmt.Printf("P50:    %v\n", p50)
		fmt.Printf("P75:    %v\n", p75)
		fmt.Printf("P90:    %v\n", p90)
		fmt.Printf("P95:    %v\n", p95)
		fmt.Printf("P99:    %v\n", p99)
		fmt.Printf("Max:    %v\n", max)
		fmt.Printf("Avg:    %v\n", avg)
	}

	fmt.Println("\n💻 System Resources:")
	fmt.Printf("  CPU Cores:          %d\n", numCPU)
	fmt.Printf("  Goroutines:         %d\n", numGoroutines)
	fmt.Printf("  Memory Allocated:   %.2f MB\n", float64(memStats.Alloc)/1024/1024)
	fmt.Printf("  Total Memory:       %.2f MB\n", float64(memStats.TotalAlloc)/1024/1024)
	fmt.Printf("  Sys Memory:         %.2f MB\n", float64(memStats.Sys)/1024/1024)
	fmt.Printf("  GC Runs:            %d\n", memStats.NumGC)

	fmt.Println("\n========================================")
	fmt.Println("✅ Load test completed")
	fmt.Println("========================================")

	// Generate Markdown report
	generateMarkdownReport(config, duration, totalRequests, successCount,
		failureCount, firstTime, lastTime, sendDuration,
		min, max, avg, p50, p75, p90, p95, p99, numCPU, numGoroutines, &memStats, hasSendTiming)
}

func generateMarkdownReport(config Config, duration time.Duration,
	totalRequests, successCount, failureCount int64,
	firstTime, lastTime time.Time, sendDuration time.Duration,
	min, max, avg, p50, p75, p90, p95, p99 time.Duration,
	numCPU, numGoroutines int, memStats *runtime.MemStats, hasSendTiming bool) {

	// Get executable directory and create report subdirectory
	exePath, err := os.Executable()
	if err != nil {
		fmt.Printf("⚠️  Failed to get executable path: %v\n", err)
		return
	}
	exeDir := filepath.Dir(exePath)
	reportDir := filepath.Join(exeDir, "report", "concurrent")

	if err := os.MkdirAll(reportDir, 0755); err != nil {
		fmt.Printf("⚠️  Failed to create report directory: %v\n", err)
		return
	}

	filename := filepath.Join(reportDir, fmt.Sprintf("loadtest-report-%s.md", time.Now().Format("20060102-150405")))
	file, err := os.Create(filename)
	if err != nil {
		fmt.Printf("⚠️  Failed to create markdown report: %v\n", err)
		return
	}
	defer file.Close()

	// Build request sending speed section conditionally
	sendingSpeedSection := ""
	if hasSendTiming {
		sendingSpeedSection = fmt.Sprintf(`
## 🚀 Request Sending Speed

| Metric | Value |
|--------|-------|
| First Request Sent | %s |
| Last Request Sent | %s |
| All Requests Sent In | %.3f ms |
| Sending Rate | %.0f req/ms |

---
`, firstTime.Format("15:04:05.000"), lastTime.Format("15:04:05.000"),
			sendDuration.Seconds()*1000, float64(totalRequests)/sendDuration.Seconds()/1000)
	}

	report := fmt.Sprintf(`# Ticketing System Load Test

**Run at:** %s
**Environment:** %s (CPUs: %d)
**Test Duration:** %.2fs

*Configuration: Concurrency=%d, Client Pool=%d, Event ID=%d, Mode=%s, Seats per Booking=1-4 (random)*

---

## Performance Results

| Metric | Value |
|--------|-------|
| Total Requests | %d |
| Successful | %d |
| Failed | %d |
| RPS (Requests/sec) | %.2f |
| Success Rate | %.2f%% |

---

## Latency Distribution

| Percentile | Latency |
|------------|---------|
| Min | %v |
| P50 | %v |
| P75 | %v |
| P90 | %v |
| P95 | %v |
| P99 | %v |
| Max | %v |
| Avg | %v |

---
%s
## System Resources

| Resource | Value |
|----------|-------|
| CPU Cores | %d |
| Goroutines | %d |
| Memory Allocated | %.2f MB |
| GC Runs | %d |

---

*Report generated by Go Load Test Tool*
`,
		time.Now().Format("Mon 02 Jan 2006, 15:04"),
		config.Host,
		numCPU,
		duration.Seconds(),
		config.Concurrency,
		config.ClientPoolSize,
		config.EventID,
		config.Mode,
		totalRequests,
		successCount,
		failureCount,
		float64(totalRequests)/duration.Seconds(),
		float64(successCount)/float64(totalRequests)*100,
		min, p50, p75, p90, p95, p99, max, avg,
		sendingSpeedSection,
		numCPU,
		numGoroutines,
		float64(memStats.Alloc)/1024/1024,
		memStats.NumGC,
	)

	if _, err := file.WriteString(report); err != nil {
		fmt.Printf("⚠️  Failed to write markdown report: %v\n", err)
		return
	}

	fmt.Printf("\n📄 Markdown report generated: %s\n", filename)
}
