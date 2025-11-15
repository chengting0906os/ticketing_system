//go:build full_reserved
// +build full_reserved

// Full Reserved Load Test for Ticketing System - Maximum Throughput Mode
// - Always buys 1 ticket per request (no random quantity)
// - Supports up to 500 concurrent workers
// - Optimized for fastest send rate
// Build with: go build -tags full_reserved

package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"sync"
	"sync/atomic"
	"time"
)

// JSON config structure (matches script/seating_config.json)
type JSONConfig struct {
	LocalDev    EnvironmentConfig `json:"local_dev"`
	Development EnvironmentConfig `json:"development"`
	Staging     EnvironmentConfig `json:"staging"`
	Production  EnvironmentConfig `json:"production"`
}

type EnvironmentConfig struct {
	TotalSeats int       `json:"total_seats"`
	Sections   []Section `json:"sections"`
}

type Section struct {
	Name        string       `json:"name"`
	Price       int          `json:"price"`
	Subsections []Subsection `json:"subsections"`
}

type Subsection struct {
	Number      int `json:"number"`
	Rows        int `json:"rows"`
	SeatsPerRow int `json:"seats_per_row"`
}

// SubsectionTask represents a task to exhaust a subsection
type SubsectionTask struct {
	Section    Section
	Subsection Subsection
}

// SubsectionResult tracks results for a subsection
type SubsectionResult struct {
	SectionName      string
	SubsectionNumber int
	TicketsPurchased int
	BookingsMade     int
	Errors           int
	Latencies        []time.Duration // Track latency for each booking
}

// loadSeatingConfig loads seating configuration from JSON file
func loadSeatingConfig(env string) (EnvironmentConfig, error) {
	configPath := "seating_config.json"
	data, err := os.ReadFile(configPath)
	if err != nil {
		return EnvironmentConfig{}, fmt.Errorf("failed to read config file: %v", err)
	}

	var jsonConfig JSONConfig
	if err := json.Unmarshal(data, &jsonConfig); err != nil {
		return EnvironmentConfig{}, fmt.Errorf("failed to parse JSON: %v", err)
	}

	var config EnvironmentConfig
	switch env {
	case "production":
		config = jsonConfig.Production
	case "staging":
		config = jsonConfig.Staging
	case "development":
		config = jsonConfig.Development
	default: // local_dev
		config = jsonConfig.LocalDev
	}

	return config, nil
}

// login performs user login and returns cookie jar with session
func login(client *http.Client, host string, email, password string) error {
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
		return fmt.Errorf("login failed: %s, body: %s", resp.Status, string(bodyBytes))
	}

	return nil
}

// BookingResult represents the result of an async booking request
type BookingResult struct {
	TicketsPurchased int
	SoldOut          bool
	Err              error
	Latency          time.Duration
}

// buyTicketsAsync sends a booking request asynchronously and returns a channel for the result
// This allows non-blocking request sending while tracking responses
func buyTicketsAsync(client *http.Client, host string, eventID int, section string, subsection int, quantity int) <-chan BookingResult {
	resultChan := make(chan BookingResult, 1)

	go func() {
		const maxRetries = 20
		const baseDelay = 50 * time.Millisecond

		reqBody := BookingCreateRequest{
			EventID:           eventID,
			Section:           section,
			Subsection:        subsection,
			SeatSelectionMode: "best_available",
			SeatPositions:     []string{},
			Quantity:          quantity,
		}

		var lastStatusCode int
		var lastBody []byte
		start := time.Now()

		for attempt := 0; attempt < maxRetries; attempt++ {
			// Linear backoff: 50ms, 100ms, 150ms, etc.
			if attempt > 0 {
				backoff := baseDelay * time.Duration(attempt)
				time.Sleep(backoff)
			}

			body, _ := json.Marshal(reqBody)
			resp, err := client.Post(host+"/api/booking", "application/json", bytes.NewBuffer(body))
			if err != nil {
				if attempt < maxRetries-1 {
					continue
				}
				resultChan <- BookingResult{
					TicketsPurchased: 0,
					SoldOut:          false,
					Err:              fmt.Errorf("request error after %d attempts: %v", maxRetries, err),
					Latency:          time.Since(start),
				}
				return
			}

			respBody, _ := io.ReadAll(resp.Body)
			resp.Body.Close()

			lastStatusCode = resp.StatusCode
			lastBody = respBody

			// Success cases - don't retry
			if resp.StatusCode == http.StatusCreated || resp.StatusCode == http.StatusOK || resp.StatusCode == http.StatusAccepted {
				var bookingResp BookingResponse
				parseErr := json.Unmarshal(respBody, &bookingResp)
				if parseErr != nil {
					resultChan <- BookingResult{
						TicketsPurchased: 0,
						SoldOut:          false,
						Err:              fmt.Errorf("failed to parse response: %v, body: %s", parseErr, string(respBody)),
						Latency:          time.Since(start),
					}
					return
				}

				// Booking created successfully - return requested quantity
				resultChan <- BookingResult{
					TicketsPurchased: quantity,
					SoldOut:          false,
					Err:              nil,
					Latency:          time.Since(start),
				}
				return
			}

			// No seats available - stop trying this subsection
			if resp.StatusCode == 404 || (resp.StatusCode == 400 && bytes.Contains(lastBody, []byte("No available seats"))) {
				resultChan <- BookingResult{
					TicketsPurchased: 0,
					SoldOut:          true,
					Err:              nil,
					Latency:          time.Since(start),
				}
				return
			}

			// Client errors (4xx) - don't retry except 429 (rate limit)
			if resp.StatusCode >= 400 && resp.StatusCode < 500 && resp.StatusCode != http.StatusTooManyRequests {
				resultChan <- BookingResult{
					TicketsPurchased: 0,
					SoldOut:          false,
					Err:              fmt.Errorf("client error %d: %s", resp.StatusCode, string(respBody)),
					Latency:          time.Since(start),
				}
				return
			}

			// Server errors (5xx) or rate limit (429) - retry
			if attempt < maxRetries-1 {
				continue
			}
		}

		resultChan <- BookingResult{
			TicketsPurchased: 0,
			SoldOut:          false,
			Err:              fmt.Errorf("request failed after %d attempts. Last status: %d, body: %s", maxRetries, lastStatusCode, string(lastBody)),
			Latency:          time.Since(start),
		}
	}()

	return resultChan
}

// worker exhausts a single subsection with concurrent requests
//
// Concurrency Mechanism:
// - Multiple workers run in parallel (controlled by numWorkers parameter)
// - Each worker independently processes subsection tasks from a shared channel
// - Workers buy tickets with FIXED quantity of 1 (optimized for max throughput)
// - All workers share the same HTTP client with cookie jar for session reuse
// - Results are collected via a separate results channel
// - WaitGroup ensures all workers complete before final statistics
func worker(
	client *http.Client,
	host string,
	eventID int,
	tasks <-chan SubsectionTask,
	results chan<- SubsectionResult,
	wg *sync.WaitGroup,
	firstRequestTime *atomic.Value,
	lastRequestTime *atomic.Value,
	lastResponseTime *atomic.Value,
	requestCount *atomic.Int64,
	batchSize int,
) {
	defer wg.Done()

	for task := range tasks {
		subsectionTickets := 0
		subsectionBookings := 0
		subsectionErrors := 0
		var latencies []time.Duration

		// Calculate max tickets based on subsection capacity (rows × seats_per_row)
		// - local_dev: 1 × 5 = 5 tickets
		// - development: 5 × 10 = 50 tickets
		// - production: 25 × 20 = 500 tickets
		maxTicketsPerSubsection := task.Subsection.Rows * task.Subsection.SeatsPerRow

		// BATCH SEND: Configurable batch size for subsection requests
		// Fixed quantity: always buy 1 ticket per request
		quantity := 1

		// Determine effective batch size (0 means send all at once)
		effectiveBatchSize := batchSize
		if effectiveBatchSize == 0 || effectiveBatchSize > maxTicketsPerSubsection {
			effectiveBatchSize = maxTicketsPerSubsection
		}

		// ═══════════════════════════════════════════════════════════════
		// PHASE 1: Send ALL requests (fire-and-forget, no waiting)
		// ═══════════════════════════════════════════════════════════════
		var allResultChans []<-chan BookingResult

		for sent := 0; sent < maxTicketsPerSubsection; sent += effectiveBatchSize {
			// Calculate how many to send in this batch
			remaining := maxTicketsPerSubsection - sent
			currentBatchSize := effectiveBatchSize
			if currentBatchSize > remaining {
				currentBatchSize = remaining
			}

			// Send batch of requests (non-blocking)
			for i := 0; i < currentBatchSize; i++ {
				// Track first request time
				if firstRequestTime.Load() == nil {
					firstRequestTime.CompareAndSwap(nil, time.Now())
				}
				requestCount.Add(1)

				// Fire async request (doesn't block)
				resultChan := buyTicketsAsync(
					client,
					host,
					eventID,
					task.Section.Name,
					task.Subsection.Number,
					quantity,
				)
				allResultChans = append(allResultChans, resultChan)
			}
		}

		// ALL requests sent - record timing (accurate send time)
		lastRequestTime.Store(time.Now())

		// ═══════════════════════════════════════════════════════════════
		// PHASE 2: Collect ALL responses (wait for everything)
		// ═══════════════════════════════════════════════════════════════
		for _, resultChan := range allResultChans {
			result := <-resultChan

			// Track when last response was received
			lastResponseTime.Store(time.Now())

			if result.Err != nil {
				subsectionErrors++
				// Don't print individual errors to avoid spam
				continue
			}

			// Record latency
			latencies = append(latencies, result.Latency)

			if result.TicketsPurchased > 0 {
				subsectionTickets += result.TicketsPurchased
				subsectionBookings++
			}
		}

		results <- SubsectionResult{
			SectionName:      task.Section.Name,
			SubsectionNumber: task.Subsection.Number,
			TicketsPurchased: subsectionTickets,
			BookingsMade:     subsectionBookings,
			Errors:           subsectionErrors,
			Latencies:        latencies,
		}
	}
}

func main() {
	// Note: As of Go 1.20, rand is automatically seeded at program startup
	// No need to call rand.Seed() manually

	// Parse command line flags
	var (
		host          string
		eventID       int
		env           string
		numWorkers    int
		batchSize     int
	)

	flag.StringVar(&host, "host", "", "API host (overrides API_HOST env var)")
	flag.IntVar(&eventID, "event", 1, "Event ID")
	flag.StringVar(&env, "env", "local_dev", "Environment (local_dev, development, staging, production)")
	flag.IntVar(&numWorkers, "workers", 500, "Number of concurrent workers (default: 500 for max throughput)")
	flag.IntVar(&batchSize, "batch", 0, "Batch size for subsection requests (0 = send all at once, default)")
	flag.Parse()

	// Use API_HOST env var if -host flag not provided
	if host == "" {
		host = os.Getenv("API_HOST")
		if host == "" {
			host = "http://localhost" // fallback default
		}
	}

	// Load seating configuration from JSON
	config, err := loadSeatingConfig(env)
	if err != nil {
		fmt.Printf("❌ Failed to load seating config: %v\n", err)
		os.Exit(1)
	}

	totalSeats := 0
	for _, section := range config.Sections {
		for _, subsection := range section.Subsections {
			totalSeats += subsection.Rows * subsection.SeatsPerRow
		}
	}

	// Calculate subsection capacity from first subsection as example
	subsectionCapacity := config.Sections[0].Subsections[0].Rows * config.Sections[0].Subsections[0].SeatsPerRow

	fmt.Println("╔══════════════════════════════════════════════════════════════╗")
	fmt.Println("║   Full Reserved Load Test - Maximum Throughput Mode         ║")
	fmt.Println("╚══════════════════════════════════════════════════════════════╝")
	fmt.Printf("\n🌍 Environment: %s\n", env)
	fmt.Printf("📊 Total seats: %d\n", totalSeats)
	fmt.Printf("🎯 Event ID: %d\n", eventID)
	fmt.Printf("🌐 Host: %s\n", host)
	fmt.Printf("🎫 Quantity per booking: 1 ticket (FIXED - optimized for max throughput)\n")
	fmt.Printf("📦 Subsection capacity: %d seats\n", subsectionCapacity)
	fmt.Printf("👷 Concurrent workers: %d\n", numWorkers)
	fmt.Println("═══════════════════════════════════════════════════════════════")

	// Create HTTP client with cookie jar
	jar, _ := cookiejar.New(nil)
	client := &http.Client{
		Jar:     jar,
		Timeout: 30 * time.Second,
	}

	// Login with pre-seeded test user
	email := "b_1@t.com"
	password := "P@ssw0rd"

	fmt.Println("\n🔐 Logging in with pre-seeded test user...")
	fmt.Printf("   Email: %s\n", email)

	if err := login(client, host, email, password); err != nil {
		fmt.Printf("❌ Failed to login: %v\n", err)
		fmt.Println("💡 Hint: Run 'make seed' to create test users")
		os.Exit(1)
	}
	fmt.Println("✅ Logged in successfully")

	// ═══════════════════════════════════════════════════════════════
	// CONCURRENT SELLOUT MECHANISM
	// ═══════════════════════════════════════════════════════════════
	//
	// Architecture:
	//   Producer-Consumer pattern with Worker Pool
	//
	// Flow:
	//   1. Create buffered channels for tasks and results
	//   2. Spawn N worker goroutines (worker pool)
	//   3. Producer goroutine feeds subsection tasks into channel
	//   4. Workers consume tasks concurrently and buy tickets
	//   5. Results collector waits for all workers to finish
	//   6. Main goroutine aggregates results from results channel
	//
	// Concurrency Features:
	//   - Non-blocking: Workers process tasks independently
	//   - Scalable: Number of workers adjustable via -workers flag
	//   - Thread-safe: Atomic counters for metrics aggregation
	//   - Session reuse: All workers share same HTTP client
	//
	// ═══════════════════════════════════════════════════════════════
	fmt.Println("\n🚀 Starting concurrent sellout (per-subsection exhaustion)...")
	fmt.Println("═══════════════════════════════════════════════════════════════")

	startTime := time.Now()

	// Create task channel and results channel
	tasks := make(chan SubsectionTask, 100)
	results := make(chan SubsectionResult, 100)

	// Request timing tracking
	var firstRequestTime atomic.Value  // When first request was sent
	var lastRequestTime atomic.Value   // When last request was sent
	var lastResponseTime atomic.Value  // When last response was received
	var requestCount atomic.Int64      // Total number of requests sent

	// Start workers (Worker Pool Pattern)
	fmt.Printf("\n   👷 Starting %d workers...\n", numWorkers)
	var wg sync.WaitGroup
	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go worker(client, host, eventID, tasks, results, &wg, &firstRequestTime, &lastRequestTime, &lastResponseTime, &requestCount, batchSize)
	}
	fmt.Printf("   ✅ All workers ready\n\n")

	// Producer: Send all subsection tasks to channel
	totalTasks := len(config.Sections) * 10
	fmt.Printf("   📋 Queueing %d subsection tasks for workers...\n", totalTasks)
	go func() {
		for _, section := range config.Sections {
			for _, subsection := range section.Subsections {
				tasks <- SubsectionTask{
					Section:    section,
					Subsection: subsection,
				}
			}
		}
		close(tasks) // Signal no more tasks
	}()

	// Results Collector: Close results channel when all workers done
	go func() {
		wg.Wait()      // Wait for all workers to finish
		close(results) // Signal no more results
	}()

	// Aggregate metrics
	var totalTickets atomic.Int64
	var totalBookings atomic.Int64
	var totalErrors atomic.Int64
	completedSubsections := 0
	totalSubsections := len(config.Sections) * 10 // 10 subsections per section

	// Collect all latencies
	var allLatencies []time.Duration

	for result := range results {
		totalTickets.Add(int64(result.TicketsPurchased))
		totalBookings.Add(int64(result.BookingsMade))
		totalErrors.Add(int64(result.Errors))
		completedSubsections++

		// Collect latencies (no mutex needed - single goroutine access)
		allLatencies = append(allLatencies, result.Latencies...)

		// Current totals
		currentTickets := totalTickets.Load()
		currentBookings := totalBookings.Load()
		currentErrors := totalErrors.Load()
		progress := float64(currentTickets) / float64(totalSeats) * 100

		// Progress indicator every 10 subsections
		if completedSubsections%10 == 0 {
			elapsed := time.Since(startTime)
			fmt.Printf("\n   📊 Progress: %d/%d subsections (%.1f%% complete)\n",
				completedSubsections, totalSubsections, float64(completedSubsections)/float64(totalSubsections)*100)
			fmt.Printf("      Tickets: %d/%d (%.1f%%), Bookings: %d, Errors: %d\n",
				currentTickets, totalSeats, progress, currentBookings, currentErrors)
			fmt.Printf("      Elapsed: %.1fs, Rate: %.1f tickets/sec\n\n",
				elapsed.Seconds(), float64(currentTickets)/elapsed.Seconds())
		}
	}

	duration := time.Since(startTime)

	// Calculate latency statistics
	var min, max, avg, p50, p75, p90, p95, p99 time.Duration
	if len(allLatencies) > 0 {
		sort.Slice(allLatencies, func(i, j int) bool {
			return allLatencies[i] < allLatencies[j]
		})

		p50 = allLatencies[len(allLatencies)*50/100]
		p75 = allLatencies[len(allLatencies)*75/100]
		p90 = allLatencies[len(allLatencies)*90/100]
		p95 = allLatencies[len(allLatencies)*95/100]
		p99 = allLatencies[len(allLatencies)*99/100]
		min = allLatencies[0]
		max = allLatencies[len(allLatencies)-1]

		var sum time.Duration
		for _, lat := range allLatencies {
			sum += lat
		}
		avg = sum / time.Duration(len(allLatencies))
	}

	// Get system resources
	numCPU := runtime.NumCPU()
	numGoroutines := runtime.NumGoroutine()
	var memStats runtime.MemStats
	runtime.ReadMemStats(&memStats)

	// Final statistics
	fmt.Println("\n═══════════════════════════════════════════════════════════════")
	fmt.Println("📊 FINAL STATISTICS")
	fmt.Println("═══════════════════════════════════════════════════════════════")
	tickets := totalTickets.Load()
	bookings := totalBookings.Load()
	errors := totalErrors.Load()

	fmt.Printf("Total tickets purchased: %d / %d (%.1f%%)\n", tickets, totalSeats, float64(tickets)/float64(totalSeats)*100)
	fmt.Printf("Total bookings:          %d\n", bookings)
	avgPerBooking := 0.0
	if bookings > 0 {
		avgPerBooking = float64(tickets) / float64(bookings)
	}
	fmt.Printf("Average per booking:     %.2f tickets\n", avgPerBooking)
	fmt.Printf("Errors:                  %d\n", errors)

	// Calculate and display timing metrics
	totalRequests := requestCount.Load()
	var requestSendDuration time.Duration
	var responseCompleteDuration time.Duration

	if firstRequestTime.Load() != nil && lastRequestTime.Load() != nil {
		first := firstRequestTime.Load().(time.Time)
		lastSent := lastRequestTime.Load().(time.Time)
		requestSendDuration = lastSent.Sub(first)

		fmt.Printf("\n📤 Request Sending Phase:\n")
		fmt.Printf("  Total requests sent:       %d\n", totalRequests)
		fmt.Printf("  Time to send all:          %.3fs\n", requestSendDuration.Seconds())
		if requestSendDuration.Seconds() > 0 {
			fmt.Printf("  Send rate:                 %.2f requests/sec\n", float64(totalRequests)/requestSendDuration.Seconds())
		}
	}

	if firstRequestTime.Load() != nil && lastResponseTime.Load() != nil {
		first := firstRequestTime.Load().(time.Time)
		lastReceived := lastResponseTime.Load().(time.Time)
		responseCompleteDuration = lastReceived.Sub(first)

		fmt.Printf("\n📥 Response Completion Phase:\n")
		fmt.Printf("  Time to receive all:       %.3fs\n", responseCompleteDuration.Seconds())
		if responseCompleteDuration.Seconds() > 0 {
			fmt.Printf("  Actual throughput:         %.2f tickets/sec\n", float64(tickets)/responseCompleteDuration.Seconds())
			fmt.Printf("  Actual booking rate:       %.2f bookings/sec\n", float64(bookings)/responseCompleteDuration.Seconds())
		}
	}

	fmt.Printf("\n⏱️  Total Duration:           %.2fs (%.2f min)\n", duration.Seconds(), duration.Minutes())

	if len(allLatencies) > 0 {
		fmt.Println("\n⏱️  Latency Distribution:")
		fmt.Printf("  Min:    %v\n", min)
		fmt.Printf("  P50:    %v\n", p50)
		fmt.Printf("  P75:    %v\n", p75)
		fmt.Printf("  P90:    %v\n", p90)
		fmt.Printf("  P95:    %v\n", p95)
		fmt.Printf("  P99:    %v\n", p99)
		fmt.Printf("  Max:    %v\n", max)
		fmt.Printf("  Avg:    %v\n", avg)
	}

	fmt.Println("\n💻 System Resources:")
	fmt.Printf("  CPU Cores:          %d\n", numCPU)
	fmt.Printf("  Goroutines:         %d\n", numGoroutines)
	fmt.Printf("  Memory Allocated:   %.2f MB\n", float64(memStats.Alloc)/1024/1024)
	fmt.Printf("  Total Memory:       %.2f MB\n", float64(memStats.TotalAlloc)/1024/1024)
	fmt.Printf("  GC Runs:            %d\n", memStats.NumGC)
	fmt.Println("═══════════════════════════════════════════════════════════════")

	if tickets == int64(totalSeats) {
		fmt.Println("🎉 All seats purchased! Complete sellout!")
	} else if tickets >= int64(float64(totalSeats)*0.95) {
		fmt.Println("✅ Near-complete sellout (>95%)")
	}

	fmt.Println("\n✅ Concurrent sellout test complete!")

	// Generate Markdown Report
	generateMarkdownReport(
		env, host, eventID, numWorkers, subsectionCapacity,
		totalSeats, tickets, bookings, errors, avgPerBooking,
		duration, requestSendDuration, responseCompleteDuration, totalRequests, startTime,
		min, max, avg, p50, p75, p90, p95, p99,
		numCPU, numGoroutines, &memStats,
	)
}

// generateMarkdownReport creates a detailed test report in Markdown format
func generateMarkdownReport(
	env, host string, eventID, numWorkers, subsectionCapacity, totalSeats int,
	tickets, bookings, errors int64, avgPerBooking float64,
	duration, requestSendDuration, responseCompleteDuration time.Duration,
	totalRequests int64, startTime time.Time,
	min, max, avg, p50, p75, p90, p95, p99 time.Duration,
	numCPU, numGoroutines int, memStats *runtime.MemStats,
) {
	// Create report directory
	reportDir := filepath.Join(".", "report", "full_reserved")
	if err := os.MkdirAll(reportDir, 0755); err != nil {
		fmt.Printf("⚠️  Failed to create report directory: %v\n", err)
		return
	}

	filename := filepath.Join(reportDir, fmt.Sprintf("full-reserved-loadtest-report-%s.md", time.Now().Format("20060102-150405")))
	file, err := os.Create(filename)
	if err != nil {
		fmt.Printf("⚠️  Failed to create markdown report: %v\n", err)
		return
	}
	defer file.Close()

	successRate := 100.0
	if totalSeats > 0 {
		successRate = float64(tickets) / float64(totalSeats) * 100
	}

	report := fmt.Sprintf(`# Full Reserved Seat Load Test Report (Maximum Throughput Mode)

**Run at:** %s
**Environment:** %s
**Test Duration:** %.2fs (%.2f min)

*Configuration: Workers=%d, Event ID=%d, Fixed Quantity=1 ticket/booking, Subsection Capacity=%d seats*

---

## 🎯 Test Results

| Metric | Value |
|--------|-------|
| Total Seats Available | %d |
| Tickets Purchased | %d (%.1f%%) |
| Total Bookings | %d |
| Average per Booking | %.2f tickets |
| Errors | %d |

---

## ⚡ Performance Metrics

### 📤 Request Sending Phase
| Metric | Value |
|--------|-------|
| Total Requests Sent | %d |
| Time to Send All | %.3fs |
| Send Rate | %.2f requests/sec |

### 📥 Response Completion Phase
| Metric | Value |
|--------|-------|
| Time to Receive All | %.3fs |
| Actual Throughput | %.2f tickets/sec |
| Actual Booking Rate | %.2f bookings/sec |

### ⏱️ Total Duration
| Metric | Value |
|--------|-------|
| Total Test Duration | %.2fs (%.2f min) |

---

## ⏱️  Latency Distribution

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

## 💻 System Resources

| Resource | Value |
|----------|-------|
| CPU Cores | %d |
| Goroutines | %d |
| Memory Allocated | %.2f MB |
| Total Memory | %.2f MB |
| GC Runs | %d |

---

## 🏗️ Concurrency Architecture

### Worker Pool Pattern
- **Workers**: %d concurrent goroutines
- **Task Distribution**: Producer-Consumer via buffered channels
- **Session Management**: Shared HTTP client with cookie jar
- **Synchronization**: WaitGroup for graceful shutdown

### Purchase Strategy
- **Fixed Quantity**: 1 ticket per booking (optimized for max throughput)
- **Max per Subsection**: %d tickets (rows × seats_per_row)
- **Retry Logic**: 20 attempts with 50ms linear backoff
- **Environment-Adaptive**: Capacity scales with environment
- **Async Requests**: Non-blocking request sending with response tracking

---

## 📊 Test Configuration

| Parameter | Value |
|-----------|-------|
| Environment | %s |
| API Host | %s |
| Event ID | %d |
| Workers | %d |
| Test Start | %s |

---

## 🎉 Result Summary

**Completion:** %.1f%% of total seats purchased

`,
		time.Now().Format("Mon 02 Jan 2006, 15:04"),
		env,
		duration.Seconds(),
		duration.Minutes(),
		numWorkers,
		eventID,
		subsectionCapacity,
		totalSeats,
		tickets,
		successRate,
		bookings,
		avgPerBooking,
		errors,
		// Request Sending Phase metrics
		totalRequests,
		requestSendDuration.Seconds(),
		func() float64 {
			if requestSendDuration.Seconds() > 0 {
				return float64(totalRequests) / requestSendDuration.Seconds()
			}
			return 0
		}(),
		// Response Completion Phase metrics
		responseCompleteDuration.Seconds(),
		func() float64 {
			if responseCompleteDuration.Seconds() > 0 {
				return float64(tickets) / responseCompleteDuration.Seconds()
			}
			return 0
		}(),
		func() float64 {
			if responseCompleteDuration.Seconds() > 0 {
				return float64(bookings) / responseCompleteDuration.Seconds()
			}
			return 0
		}(),
		// Total Duration
		duration.Seconds(),
		duration.Minutes(),
		// Latency Distribution
		min, p50, p75, p90, p95, p99, max, avg,
		numCPU,
		numGoroutines,
		float64(memStats.Alloc)/1024/1024,
		float64(memStats.TotalAlloc)/1024/1024,
		memStats.NumGC,
		numWorkers,
		subsectionCapacity,
		env,
		host,
		eventID,
		numWorkers,
		startTime.Format("2006-01-02 15:04:05"),
		successRate,
	)

	// Add result verdict
	if tickets == int64(totalSeats) {
		report += "🎉 **Status:** Complete Sellout! All seats successfully purchased.\n"
	} else if tickets >= int64(float64(totalSeats)*0.95) {
		report += "✅ **Status:** Near-complete sellout (>95% purchased).\n"
	} else {
		report += fmt.Sprintf("⚠️  **Status:** Partial completion (%.1f%% purchased).\n", successRate)
	}

	report += "\n---\n\n*Report generated by Go Full Reserved Load Test Tool (Maximum Throughput Mode)*\n"

	if _, err := file.WriteString(report); err != nil {
		fmt.Printf("⚠️  Failed to write report: %v\n", err)
		return
	}

	fmt.Printf("\n📄 Report saved to: %s\n", filename)
}
