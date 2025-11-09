package main

// Shared API Request/Response Types

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
	ID         string  `json:"id"`          // UUID7 string
	BuyerID    int     `json:"buyer_id"`
	EventID    int     `json:"event_id"`
	TotalPrice int     `json:"total_price"`
	Status     string  `json:"status"`
	CreatedAt  string  `json:"created_at"`
	PaidAt     *string `json:"paid_at"`
}
