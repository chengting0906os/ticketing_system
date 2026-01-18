# Reservation - PRD

## 1. Overview

The Reservation module manages seat status changes, including Reserve and Release operations. This service receives events from Ticketing Service via Kafka, operates Kvrocks to manage seat status, and writes results to PostgreSQL.

> **Note**: Kvrocks only tracks AVAILABLE/RESERVED two states. PostgreSQL is the source of truth for SOLD/COMPLETED status.

---

## 2. User Story

- As the system, I need to receive reservation requests and update seat status to prevent overselling
- As the system, I need to write to PostgreSQL first then sync to Kvrocks to ensure data consistency
- As the system, I need to receive cancellation requests and release seats for other users

---

## 3. Business Rules

1. **Seat Status**: Kvrocks tracks two states - `AVAILABLE` and `RESERVED`. SOLD status is managed by PostgreSQL.
2. **Atomic Operations**: All seat operations use Lua Script to ensure atomicity
3. **Selection Mode**:
   - `manual`: Manual seat selection, requires specified seat IDs
   - `best_available`: System automatically selects best available consecutive seats
4. **Reservation Quantity Limit**: Maximum 4 seats per reservation
5. **Idempotency**: Use booking_id to ensure duplicate messages are not processed again
6. **Consecutive Seat Priority**: best_available mode prioritizes consecutive seats in the same row
7. **Smart Fallback**: When best_available cannot find consecutive seats, uses largest consecutive block combination
8. **Failure Handling**: When reservation fails, create FAILED status booking and notify user via SSE
9. **Real-time Broadcast**: Push to SSE clients via Pub/Sub after seat status changes

---

## 4. Acceptance

### Seat Reservation

- [x] Manual selection mode can successfully reserve specified seats
- [x] Best available mode can automatically select consecutive seats
- [x] Reserving already reserved seats returns failure
- [x] Entire reservation fails when some seats are unavailable (atomicity)
- [x] Seat status becomes RESERVED after successful reservation
- [x] Write to PostgreSQL (booking + tickets) after successful reservation
- [x] Create FAILED status booking when reservation fails
- [x] Send SSE notification via Pub/Sub after reservation completes
- [x] Reservation requests exceeding 4 seats are rejected

### Seat Release

- [x] Can batch release multiple seats
- [x] Seat status becomes AVAILABLE after successful release
- [x] Supports partial success (some seats released successfully, some failed)

### Best Available Algorithm

- [x] Prioritize consecutive seats in the same row
- [x] If insufficient consecutive seats in same row, try next row
- [x] When no consecutive seats available, select scattered available seats

---

## 5. Test Scenarios

### Integration Tests

- [reserve_seats_atomic_integration_test.py](../../test/service/reservation/reserve_seats_atomic_integration_test.py)

### Unit Tests

- [seat_reservation_use_case_unit_test.py](../../test/service/reservation/seat_reservation_use_case_unit_test.py)
- [seat_finder_unit_test.py](../../test/service/reservation/seat_finder_unit_test.py)
- [seat_state_command_handler_unit_test.py](../../test/service/reservation/seat_state_command_handler_unit_test.py)
- [atomic_reservation_executor_unit_test.py](../../test/service/reservation/atomic_reservation_executor_unit_test.py)

---

## 6. Technical Specification

### 6.1 MQ Topics (Input)

| Topic Pattern | Description | Producer | Message Type |
| ------------- | ----------- | -------- | ------------ |
| `event-id-{id}______reserve-seats-request______booking___to___reservation` | Seat Reservation Request | Ticketing Service | BookingCreatedDomainEvent |
| `event-id-{id}______release-ticket-status-to-available-in-kvrocks______ticketing___to___reservation` | Seat Release Request | Ticketing Service | BookingCancelledEvent |

### 6.2 Seat Status (Kvrocks)

| Status | Value | Description |
| ------ | ----- | ----------- |
| AVAILABLE | 0 | Available for reservation |
| RESERVED | 1 | Reserved (pending payment) |

> **Note**: SOLD status is managed by PostgreSQL ticket.status, Kvrocks does not track this status.

### 6.3 Request/Result DTOs

#### ReservationRequest

| Field | Type | Description |
| ----- | ---- | ----------- |
| `booking_id` | str | Booking ID (UUID7) |
| `buyer_id` | int | Buyer ID |
| `event_id` | int | Event ID |
| `selection_mode` | str | Selection Mode (manual/best_available) |
| `section_filter` | str | Section |
| `subsection_filter` | int | Subsection |
| `quantity` | int | Seat Quantity |
| `seat_positions` | List[str] | Seat List (for manual mode) |
| `config` | SubsectionConfig | Subsection Config (rows, cols, price) |

#### ReservationResult

| Field | Type | Description |
| ----- | ---- | ----------- |
| `success` | bool | Is Successful |
| `booking_id` | str | Booking ID |
| `reserved_seats` | List[str] | Successfully Reserved Seat List |
| `total_price` | int | Total Price |
| `error_message` | str | Error Message (on failure) |
| `event_id` | int | Event ID |

#### ReleaseSeatsBatchRequest

| Field | Type | Description |
| ----- | ---- | ----------- |
| `seat_positions` | List[str] | Seat List, format: `"{row}-{seat}"` |
| `event_id` | int | Event ID |
| `section` | str | Section |
| `subsection` | int | Subsection |

### 6.4 Kvrocks Data Structure

| Key Pattern | Type | Description |
| ----------- | ---- | ----------- |
| `seats_bf:{event_id}:{section}-{subsection}` | BITFIELD | Seat Status (1 bit per seat: u1, 0=available, 1=reserved) |
| `seats_config:{event_id}:{section}-{subsection}` | HASH | Subsection Config (rows, cols, price) |
| `subsection_stats:{event_id}:{section}-{subsection}` | HASH | Statistics (available, reserved) |
| `seat_booking:{event_id}:{section}-{subsection}:{row}-{seat}` | STRING | Seat to booking_id mapping |

### 6.5 Implementation

#### MQ Consumer

- [reservation_mq_consumer.py](../../src/service/reservation/driving_adapter/reservation_mq_consumer.py)
- [start_reservation_consumer.py](../../src/service/reservation/driving_adapter/start_reservation_consumer.py)

#### Use Cases (Command)

- [seat_reservation_use_case.py](../../src/service/reservation/app/command/seat_reservation_use_case.py)
- [seat_release_use_case.py](../../src/service/reservation/app/command/seat_release_use_case.py)

#### Interfaces

- [i_seat_state_command_handler.py](../../src/service/reservation/app/interface/i_seat_state_command_handler.py)
- [i_booking_command_repo.py](../../src/service/reservation/app/interface/i_booking_command_repo.py)

#### Driven Adapters

- [seat_state_command_handler_impl.py](../../src/service/reservation/driven_adapter/seat_state_command_handler_impl.py)
- [booking_command_repo_impl.py](../../src/service/reservation/driven_adapter/repo/booking_command_repo_impl.py)

#### Reservation Helpers

- [atomic_reservation_executor.py](../../src/service/reservation/driven_adapter/reservation_helper/atomic_reservation_executor.py)
- [seat_finder.py](../../src/service/reservation/driven_adapter/reservation_helper/seat_finder.py)
- [release_executor.py](../../src/service/reservation/driven_adapter/reservation_helper/release_executor.py)

### 6.6 Architecture Flow

```
Ticketing Service ──Kafka──> Reservation Service ──> PostgreSQL + Kvrocks + Pub/Sub
```

**Flow:**

1. Ticketing Service sends Domain Event to Kafka (Reserve/Release use same topic: `seat_reservation`)
2. Reservation Consumer receives message, executes corresponding UseCase
3. Kvrocks Find Seats (Reserve only: BITFIELD GET to query available seats)
4. PostgreSQL Write (booking + tickets status update)
5. Kvrocks Set Seats (BITFIELD SET to update seat status)
6. Send SSE notification to frontend via Pub/Sub

**Detailed Workflow Documents**:
- [Reservation Workflow](RESERVATION_1_RESERVATION_WORKFLOW_SPEC.md)
- [Release Workflow](RESERVATION_2_RELEASE_WORKFLOW_SPEC.md)
- [Find Best Available Seats](RESERVATION_3_FIND_BEST_AVAILABLE_SEATS_SPEC.md)
