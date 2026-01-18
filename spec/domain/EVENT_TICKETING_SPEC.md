# Event Ticketing - PRD

## 1. Overview

The Event Ticketing module manages event and ticket creation, queries, and real-time seat status updates. Sellers can create events with auto-generated seat tickets, buyers can query available events, and receive real-time seat status updates via SSE.

---

## 2. User Story

- As a Seller, I need to create events with auto-generated seat tickets for buyers to purchase
- As a Seller, I need to view all my events to manage event status
- As a Buyer, I need to view available events to choose which event to attend
- As a User, I need to view event details and remaining seat counts to decide which section to purchase
- As a User, I need to receive real-time seat status updates to see the latest seat availability

---

## 3. Business Rules

1. **Event Creation Permission**: Only Sellers can create events
2. **Auto Ticket Generation**: Auto-generate all seat tickets based on `seating_config` when creating event
3. **Event Status Flow**: DRAFT → AVAILABLE → SOLD_OUT / COMPLETED / ENDED
4. **Event List Filtering**:
   - Seller: Can view all their events (any status)
   - Buyer: Can only view events with `is_active=true` and `status=available`
5. **Seating Config Format** (Compact Format):
   ```json
   {
     "rows": 25,
     "cols": 20,
     "sections": [{ "name": "A", "price": 2000, "subsections": 2 }]
   }
   ```
6. **Price Validation**: Ticket price must be >= 0
7. **Compensation Transaction**: If Kvrocks initialization fails, rollback created Event and Ticket
8. **Real-time Status Push**: Use Redis Pub/Sub subscription pattern to push to SSE clients when seat status changes

---

## 4. Acceptance

### Event CRUD

- [x] Seller can successfully create event with auto-generated tickets
- [x] After event creation, ticket count = rows × cols × sections × subsections
- [x] Buyer cannot create event (403)
- [x] Event name cannot be empty (400)
- [x] Ticket price cannot be negative (400)
- [x] Invalid seating_config returns 400
- [x] Seller can view all their events (including non-available status)
- [x] Buyer can only see is_active=true and status=available events
- [x] Query single event returns real-time remaining seat count (from Kvrocks)
- [x] Query single event returns all ticket info
- [x] Query non-existent event returns 404
- [x] Execute compensation transaction when Kvrocks initialization fails (delete created data)

### SSE Real-time Updates

- [x] SSE connection immediately returns initial status
- [x] Seat status changes are pushed to all subscribers via Pub/Sub
- [x] Multiple SSE clients can subscribe to the same event simultaneously
- [x] SSE connection to non-existent event returns 404

---

## 5. Test Scenarios

### Integration Tests (BDD)

- [event_creation.feature](../../test/service/ticketing/event_ticketing/event_creation.feature)
- [event_list_validation.feature](../../test/service/ticketing/event_ticketing/event_list_validation.feature)
- [event_get_integration_test.feature](../../test/service/ticketing/event_ticketing/event_get_integration_test.feature)
- [event_subsection_seats_list_integration_test.feature](../../test/service/ticketing/event_ticketing/event_subsection_seats_list_integration_test.feature)
- [event_status_sse_stream_integration_test.feature](../../test/service/ticketing/event_ticketing/event_status_sse_stream_integration_test.feature)

### Unit Tests

- [init_event_and_tickets_use_case_unit_test.py](../../test/service/ticketing/event_ticketing/init_event_and_tickets_use_case_unit_test.py)
- [init_seats_handler_unit_test.py](../../test/service/ticketing/event_ticketing/init_seats_handler_unit_test.py)
- [real_time_event_state_subscriber_unit_test.py](../../test/service/ticketing/event_ticketing/real_time_event_state_subscriber_unit_test.py)

---

## 6. Technical Specification

### 6.1 API Endpoints

| Method | Endpoint                                                                     | Description                         | Permission | Success | Error    |
| ------ | ---------------------------------------------------------------------------- | ----------------------------------- | ---------- | ------- | -------- |
| POST   | `/api/event`                                                                 | Create Event                        | Seller     | 201     | 400, 403 |
| GET    | `/api/event`                                                                 | List All Purchasable Events         | Public     | 200     | -        |
| GET    | `/api/event?seller_id={id}`                                                  | List All Seller Events              | Public     | 200     | -        |
| GET    | `/api/event/{event_id}`                                                      | Get Event Details (with section status) | Public     | 200     | 404      |
| GET    | `/api/event/{event_id}/sections/{section}/subsection/{subsection}/seats`     | Get Subsection Seat List            | Public     | 200     | 404      |
| GET    | `/api/event/{event_id}/sse`                                                  | Subscribe Event Status (SSE)        | Public     | 200     | 404      |

### 6.2 Model

#### EventModel

| Field            | Type  | Description                                                            |
| ---------------- | ----- | ---------------------------------------------------------------------- |
| `id`             | int   | Primary key (auto)                                                     |
| `name`           | str   | Event Name                                                             |
| `description`    | str   | Event Description                                                      |
| `seller_id`      | int   | FK to User                                                             |
| `is_active`      | bool  | Is Published (default=True)                                            |
| `status`         | str   | Event Status (default='available')                                     |
| `venue_name`     | str   | Venue Name                                                             |
| `seating_config` | JSON  | Seating Configuration                                                  |
| `stats`          | JSONB | Event Statistics (available, reserved, sold, total), auto-updated by trigger |

#### TicketModel

| Field         | Type     | Description                         |
| ------------- | -------- | ----------------------------------- |
| `id`          | int      | Primary key (auto)                  |
| `event_id`    | int      | Event ID (indexed)                  |
| `section`     | str      | Section Name                        |
| `subsection`  | int      | Subsection Number                   |
| `row_number`  | int      | Row Number                          |
| `seat_number` | int      | Seat Number                         |
| `price`       | int      | Ticket Price                        |
| `status`      | str      | Ticket Status (default='available') |
| `buyer_id`    | int      | Buyer ID (nullable, indexed)        |
| `reserved_at` | datetime | Reserved At (nullable)              |
| `created_at`  | datetime | Created At (auto)                   |
| `updated_at`  | datetime | Updated At (auto)                   |

**Unique Constraint**: `(event_id, section, subsection, row_number, seat_number)`

### 6.3 Request/Response Schema

See [event_schema.py](../../src/service/ticketing/driving_adapter/schema/event_schema.py)

#### SSE Event Format

```
event: initial_status
data: {"event_type": "initial_status", "event_id": 1, "sections": [...], "total_sections": 4}

event: status_update
data: {"event_type": "status_update", "event_id": 1, "sections": [...], "total_sections": 4}
```

### 6.4 SSE Architecture (Pub/Sub Pattern)

1. When SSE client connects, query Kvrocks for initial status and push `initial_status`
2. Subscribe to Redis Pub/Sub channel `event_state_updates:{event_id}`
3. After Reservation Service updates seats, publish to channel via `IPubSubHandler.broadcast_event_state()`
4. SSE endpoint pushes `status_update` to client after receiving message
5. Auto-cleanup connection when client disconnects

### 6.5 Implementation

#### Core Domain

- [event_ticketing_aggregate.py](../../src/service/ticketing/domain/aggregate/event_ticketing_aggregate.py)

#### HTTP Controller

- [event_ticketing_controller.py](../../src/service/ticketing/driving_adapter/http_controller/event_ticketing_controller.py)
- [event_schema.py](../../src/service/ticketing/driving_adapter/schema/event_schema.py)

#### Use Cases

- [create_event_and_tickets_use_case.py](../../src/service/ticketing/app/command/create_event_and_tickets_use_case.py)
- [list_events_use_case.py](../../src/service/ticketing/app/query/list_events_use_case.py)

#### Pub/Sub Components

- [pubsub_handler_impl.py](../../src/service/shared_kernel/driven_adapter/pubsub_handler_impl.py)
- [real_time_event_state_subscriber.py](../../src/service/ticketing/driven_adapter/state/real_time_event_state_subscriber.py)

#### State Handler

- [init_event_and_tickets_state_handler_impl.py](../../src/service/ticketing/driven_adapter/state/init_event_and_tickets_state_handler_impl.py)
- [seat_state_query_handler_impl.py](../../src/service/ticketing/driven_adapter/state/seat_state_query_handler_impl.py)
