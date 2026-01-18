# Booking - PRD

## 1. Overview

The Booking module manages ticket booking creation, queries, payment, and cancellation workflows. Buyers can choose manual seat selection or best available seat mode for booking. The system collaborates with Reservation Service through Kafka event-driven architecture to lock seats, and pushes booking status updates in real-time via SSE.

---

## 2. User Story

- As a Buyer, I need to select seats and create a booking to lock the desired seats
- As a Buyer, I need to use the best available seat feature to quickly complete a booking
- As a Buyer, I need to view my booking details to confirm seat information
- As a Buyer, I need to cancel unpaid bookings to release seats for others
- As a Buyer, I need to complete booking payment to confirm successful purchase
- As a Buyer, I need to receive real-time booking status updates to know if seat reservation was successful
- As a Seller, I need to view all bookings for my events to manage sales status

---

## 3. Business Rules

1. **Booking Quantity Limit**: Each booking requires minimum 1 ticket, maximum 4 tickets
2. **Seat Selection Mode**:
   - `manual`: Manual seat selection, requires seat_positions, count must match quantity
   - `best_available`: System automatically selects best available seats, seat_positions must be empty array
3. **Seat Format**: seat_positions format is `"row-seat"` (e.g., `"1-1"`, `"2-3"`)
4. **Fail Fast Principle**: Check seat availability before creating booking, return error immediately if insufficient
5. **Status Transition Rules**:
   - Only `processing` and `pending_payment` status can be cancelled
   - Only `pending_payment` status can be paid
   - Payment in `processing` status returns 400 "Cannot pay booking in processing state"
   - `completed`, `cancelled`, `failed` are terminal states, cannot be changed
   - Terminal state error responses (all return 400):
     - Cancel `completed` status: "Cannot cancel a completed booking"
     - Cancel `cancelled` status: "Booking already in terminal state"
     - Cancel `failed` status: "Cannot cancel failed booking"
6. **No Timeout**: `pending_payment` status has no time limit, until buyer pays or cancels
7. **Permission Control**:
   - Only the booking's buyer can cancel or pay
   - Sellers can view all bookings for their events
   - Buyers can only view their own bookings
8. **Event-Driven**: Booking creation/cancellation notifies Reservation Service via Kafka events to update seat status

---

## 4. Acceptance

### Booking Creation

- [x] Buyer can manually select 1-4 seats to create booking
- [x] Buyer can create booking using best available mode
- [x] Manual selection requires seat_positions count to match quantity
- [x] Best available mode requires seat_positions to be empty array
- [x] Booking quantity exceeding 4 returns 400
- [x] Insufficient seats returns 400 immediately (Fail Fast)
- [x] Booking status is processing after creation
- [x] BookingCreatedDomainEvent is sent after booking creation

### Booking Payment

- [x] Buyer can pay for pending_payment status bookings
- [x] Status changes to completed after successful payment
- [x] Associated ticket status changes to sold after successful payment
- [x] Paid bookings cannot be paid again
- [x] Cancelled bookings cannot be paid
- [x] processing status bookings cannot be paid (returns 400)
- [x] failed status bookings cannot be paid (returns 400)
- [x] Non-booking owner cannot pay

### Booking Cancellation

- [x] Buyer can cancel processing or pending_payment status bookings
- [x] Status changes to cancelled after cancellation
- [x] Seats are released back to available status after cancellation
- [x] Completed bookings cannot be cancelled (returns 400)
- [x] Cancelled bookings cannot be cancelled again (returns 400)
- [x] failed status bookings cannot be cancelled (returns 400)
- [x] Non-booking owner cannot cancel (returns 403)

### Booking Query

- [x] Buyer can view their own booking list
- [x] Seller can view all bookings for their events
- [x] Booking list can be filtered by status
- [x] Booking details include event info, buyer info, seat info
- [x] Query for non-existent booking returns 404

### SSE Real-time Updates

- [x] Authenticated users can connect to SSE to receive booking status updates
- [x] Unauthenticated users connecting to SSE returns 401
- [x] SSE connection auto-closes when booking reaches terminal state

---

## 5. Test Scenarios

### Integration Tests (BDD)

- [booking_creation_integration_test.feature](../../test/service/ticketing/booking/booking_creation_integration_test.feature)
- [booking_payment_integration_test.feature](../../test/service/ticketing/booking/booking_payment_integration_test.feature)
- [booking_cancellation_integration_test.feature](../../test/service/ticketing/booking/booking_cancellation_integration_test.feature)
- [booking_list_integration_test.feature](../../test/service/ticketing/booking/booking_list_integration_test.feature)
- [booking_sse_integration_test.feature](../../test/service/ticketing/booking/booking_sse_integration_test.feature)

### Unit Tests

- [create_booking_use_case_unit_test.py](../../test/service/ticketing/booking/create_booking_use_case_unit_test.py)
- [update_booking_to_cancelled_use_case_unit_test.py](../../test/service/ticketing/booking/update_booking_to_cancelled_use_case_unit_test.py)

---

## 6. Technical Specification

### 6.1 API Endpoints

| Method | Endpoint                            | Description                    | Permission    | Success | Error         |
| ------ | ----------------------------------- | ------------------------------ | ------------- | ------- | ------------- |
| POST   | `/api/booking`                      | Create Booking                 | Buyer         | 202     | 400, 401      |
| GET    | `/api/booking/{booking_id}`         | Get Booking Details            | Authenticated | 200     | 401, 404      |
| GET    | `/api/booking/my_booking`           | List My Bookings               | Authenticated | 200     | 401           |
| PATCH  | `/api/booking/{booking_id}`         | Cancel Booking                 | Buyer         | 200     | 400, 401, 404 |
| POST   | `/api/booking/{booking_id}/pay`     | Pay Booking                    | Buyer         | 200     | 400, 401, 404 |
| GET    | `/api/booking/event/{event_id}/sse` | Subscribe Booking Status (SSE) | Authenticated | 200     | 401           |

### 6.2 Model

#### BookingModel

| Field                 | Type      | Description                                                       |
| --------------------- | --------- | ----------------------------------------------------------------- |
| `id`                  | UUID      | Primary key (UUID7)                                               |
| `buyer_id`            | int       | Buyer ID (indexed)                                                |
| `event_id`            | int       | Event ID (indexed)                                                |
| `section`             | str       | Section                                                           |
| `subsection`          | int       | Subsection                                                        |
| `seat_positions`      | List[str] | Seat list (nullable), format: `"{row}-{seat}"` e.g. `["1-1", "1-2"]` |
| `quantity`            | int       | Quantity (default=0)                                              |
| `total_price`         | int       | Total Price                                                       |
| `status`              | str       | Booking Status (default='processing')                             |
| `seat_selection_mode` | str       | Seat Selection Mode                                               |
| `created_at`          | datetime  | Created At (auto)                                                 |
| `updated_at`          | datetime  | Updated At (auto)                                                 |
| `paid_at`             | datetime  | Paid At (nullable)                                                |

#### BookingStatus Enum

| Value           | Description                                              |
| --------------- | -------------------------------------------------------- |
| processing      | Processing (initial state, waiting for seat confirmation) |
| pending_payment | Pending Payment (seats reserved successfully)            |
| completed       | Completed (payment successful)                           |
| cancelled       | Cancelled                                                |
| failed          | Failed (seat reservation failed)                         |

#### Status Transition Diagram

```
                    ┌──────────────┐
                    │  processing  │
                    └──────┬───────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌──────────┐   ┌───────────────┐   ┌──────────┐
    │  failed  │   │pending_payment│   │cancelled │
    └──────────┘   └───────┬───────┘   └──────────┘
                           │                ▲
                    ┌──────┴──────┐         │
                    │             │         │
                    ▼             └─────────┘
             ┌───────────┐
             │ completed │
             └───────────┘
```

### 6.3 Request/Response Schema

- [booking_schema.py](../../src/service/ticketing/driving_adapter/schema/booking_schema.py)

### 6.4 Domain Events

| Event                     | Trigger          | Consumer            | Action                       |
| ------------------------- | ---------------- | ------------------- | ---------------------------- |
| BookingCreatedDomainEvent | Booking Created  | Reservation Service | Reserve seats in Kvrocks     |
| BookingCancelledEvent     | Booking Cancelled | Reservation Service | Release seats in Kvrocks     |

> **Note**: Payment completion directly updates PostgreSQL, no event sent to Reservation Service. Kvrocks only tracks available/reserved status.

#### BookingCreatedDomainEvent

| Field               | Type             | Description                          |
| ------------------- | ---------------- | ------------------------------------ |
| booking_id          | UUID             | Booking ID                           |
| buyer_id            | int              | Buyer ID                             |
| event_id            | int              | Event ID                             |
| total_price         | int              | Total Price                          |
| section             | str              | Section                              |
| subsection          | int              | Subsection                           |
| quantity            | int              | Quantity                             |
| seat_selection_mode | str              | Selection Mode (manual/best_available) |
| seat_positions      | List[str]        | Seat List, format: `"{row}-{seat}"`  |
| status              | BookingStatus    | Booking Status                       |
| occurred_at         | datetime         | Occurred At                          |
| config              | SubsectionConfig | Subsection Config (rows, cols, price) |

#### BookingCancelledEvent

| Field          | Type      | Description                         |
| -------------- | --------- | ----------------------------------- |
| booking_id     | UUID      | Booking ID                          |
| buyer_id       | int       | Buyer ID                            |
| event_id       | int       | Event ID                            |
| section        | str       | Section                             |
| subsection     | int       | Subsection                          |
| seat_positions | List[str] | Seat List, format: `"{row}-{seat}"` |
| cancelled_at   | datetime  | Cancelled At                        |

### 6.5 SSE Architecture

```
Browser ◄── SSE ── Controller ── subscribe ──► Kvrocks Pub/Sub
                                                     ▲
Reservation Service ─────── publish ─────────────────┘
```

**Flow:**

1. When SSE client connects, subscribe to Kvrocks pub/sub channel `booking:status:{user_id}:{event_id}`
2. Reservation Service publishes status update via `IPubSubHandler` after processing seat reservation
3. SSE endpoint pushes `status_update` event to client after receiving subscription message
4. Auto-close SSE connection when booking reaches terminal state (completed/failed/cancelled)

### 6.6 Implementation

#### Core Domain

- [booking_entity.py](../../src/service/ticketing/domain/entity/booking_entity.py)
- [booking_domain_event.py](../../src/service/ticketing/domain/domain_event/booking_domain_event.py)

#### HTTP Controller

- [booking_controller.py](../../src/service/ticketing/driving_adapter/http_controller/booking_controller.py)
- [booking_schema.py](../../src/service/ticketing/driving_adapter/schema/booking_schema.py)

#### Use Cases (Command)

- [create_booking_use_case.py](../../src/service/ticketing/app/command/create_booking_use_case.py)
- [update_booking_status_to_cancelled_use_case.py](../../src/service/ticketing/app/command/update_booking_status_to_cancelled_use_case.py)
- [mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case.py](../../src/service/ticketing/app/command/mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case.py)

#### Use Cases (Query)

- [get_booking_use_case.py](../../src/service/ticketing/app/query/get_booking_use_case.py)
- [list_bookings_use_case.py](../../src/service/ticketing/app/query/list_bookings_use_case.py)

#### Repository

- [booking_command_repo_impl.py](../../src/service/ticketing/driven_adapter/repo/booking_command_repo_impl.py)
- [booking_query_repo_impl.py](../../src/service/ticketing/driven_adapter/repo/booking_query_repo_impl.py)
