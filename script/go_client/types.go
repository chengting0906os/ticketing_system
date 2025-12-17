//go:build full_reserved
// +build full_reserved

package main

import (
	"encoding/json"
	"time"
)

// ═══════════════════════════════════════════════════════════════
// API Request/Response Types
// ═══════════════════════════════════════════════════════════════

type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type BookingCreateRequest struct {
	EventID           int      `json:"event_id"`
	Section           string   `json:"section"`
	Subsection        int      `json:"subsection"`
	SeatSelectionMode string   `json:"seat_selection_mode"`
	SeatPositions     []string `json:"seat_positions"`
	Quantity          int      `json:"quantity"`
}

type BookingResponse struct {
	ID         string  `json:"id"` // UUID7 string
	BuyerID    int     `json:"buyer_id"`
	EventID    int     `json:"event_id"`
	TotalPrice int     `json:"total_price"`
	Status     string  `json:"status"`
	CreatedAt  string  `json:"created_at"`
	PaidAt     *string `json:"paid_at"`
}

// ═══════════════════════════════════════════════════════════════
// JSON Config Types (matches script/seating_config.json)
// ═══════════════════════════════════════════════════════════════

// RawJSONConfig reads raw JSON with any environment
type RawJSONConfig map[string]json.RawMessage

// CompactEnvironmentConfig is the JSON format in seating_config.json
type CompactEnvironmentConfig struct {
	TotalSeats int              `json:"total_seats"`
	Rows       int              `json:"rows"`
	Cols       int              `json:"cols"`
	Sections   []CompactSection `json:"sections"`
}

// CompactSection uses int for subsections count
type CompactSection struct {
	Name        string `json:"name"`
	Price       int    `json:"price"`
	Subsections int    `json:"subsections"`
}

// EnvironmentConfig is the expanded format used internally
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
	Number int `json:"number"`
	Rows   int `json:"rows"`
	Cols   int `json:"cols"`
}

// ═══════════════════════════════════════════════════════════════
// Worker Types
// ═══════════════════════════════════════════════════════════════

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
	Latencies        []time.Duration
}

// BookingResult represents the result of an async booking request
type BookingResult struct {
	TicketsPurchased int
	SoldOut          bool
	Err              error
	Latency          time.Duration
}
