# Ticketing Service Specification

> **📂 Service Root**: [src/service/ticketing/](../src/service/ticketing/)
>
> **📁 Directory Structure**:
> ```
> ticketing/
> ├── driving_adapter/
> │   ├── http_controller/         # FastAPI endpoints
> │   ├── mq_consumer/             # Kafka consumers
> │   ├── model/                   # SQLAlchemy models
> │   └── schema/                  # Pydantic schemas
> ├── app/
> │   ├── command/                 # Write operations (CQRS)
> │   ├── query/                   # Read operations (CQRS)
> │   ├── service/                 # Application services
> │   └── interface/               # Port interfaces
> ├── domain/
> │   ├── entity/                  # Domain entities
> │   ├── event_ticketing_aggregate.py
> │   └── value_object/
> └── driven_adapter/
>     ├── repository/              # Data access
>     └── kafka_producer/          # Event publishing
> ```

## Architecture

See directory structure above for Hexagonal Architecture implementation.

**Key Patterns**:
- **CQRS**: [app/command/](../src/service/ticketing/app/command/) vs [app/query/](../src/service/ticketing/app/query/)
- **Aggregate Root**: [event_ticketing_aggregate.py](../src/service/ticketing/domain/event_ticketing_aggregate.py)
- **Repository**: [driven_adapter/repository/](../src/service/ticketing/driven_adapter/repository/)

## Database Schema

See SQLAlchemy models for actual schema:
- [user_model.py](../src/service/ticketing/driven_adapter/model/user_model.py) - Authentication & roles
- [event_model.py](../src/service/ticketing/driven_adapter/model/event_model.py) - Events with JSONB config
- [ticket_model.py](../src/service/ticketing/driven_adapter/model/ticket_model.py) - Tickets (unique constraint)
- [booking_model.py](../src/service/ticketing/driven_adapter/model/booking_model.py) - Bookings (M2M with tickets)

## Domain Entities

See entity implementations:
- [user_entity.py](../src/service/ticketing/domain/entity/user_entity.py) - User with role enum
- [booking_entity.py](../src/service/ticketing/domain/entity/booking_entity.py) - Booking lifecycle

## Use Cases

### Event Management
- **Create**: [create_event_and_tickets_use_case.py](../src/service/ticketing/app/command/create_event_and_tickets_use_case.py)
- **Query**: [get_event_use_case.py](../src/service/ticketing/app/query/get_event_use_case.py) | [list_events_use_case.py](../src/service/ticketing/app/query/list_events_use_case.py)

### Booking Management
- **Create**: [create_booking_use_case.py](../src/service/ticketing/app/command/create_booking_use_case.py)
- **Payment**: [mock_payment_and_update_status_to_completed_use_case.py](../src/service/ticketing/app/command/mock_payment_and_update_status_to_completed_use_case.py)
- **Cancel**: [update_booking_status_to_cancelled_use_case.py](../src/service/ticketing/app/command/update_booking_status_to_cancelled_use_case.py)
- **Query**: [get_booking_use_case.py](../src/service/ticketing/app/query/get_booking_use_case.py) | [list_bookings_use_case.py](../src/service/ticketing/app/query/list_bookings_use_case.py)

## Integration

### Kafka Topics
See [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py) `KafkaTopicBuilder` class for topic naming

### MQ Consumer
See [ticketing_mq_consumer.py](../src/service/ticketing/driving_adapter/mq_consumer/ticketing_mq_consumer.py)

See [KAFKA_SPEC.md](KAFKA_SPEC.md) for partition strategy and consumer group configuration.

### Database Schema (PostgreSQL)

> **📁 SQLAlchemy Models**:
> - [user_model.py](../src/service/ticketing/driven_adapter/model/user_model.py) - User authentication & roles
> - [event_model.py](../src/service/ticketing/driven_adapter/model/event_model.py) - Event with JSONB seating config
> - [ticket_model.py](../src/service/ticketing/driven_adapter/model/ticket_model.py) - Tickets with unique constraint
> - [booking_model.py](../src/service/ticketing/driven_adapter/model/booking_model.py) - Bookings with M2M relationship

**Key Tables**:

1. **`user`** - Authentication & Authorization
   - `role`: VARCHAR(20) - 'buyer' | 'seller'
   - `hashed_password`: VARCHAR(255) - Bcrypt encrypted
   - `is_active`, `is_verified`, `is_superuser`: Boolean flags
   - `email`: VARCHAR(255) - Unique, indexed

2. **`event`** - Event Metadata
   - `seating_config`: JSONB - Sections/subsections structure
   - `status`: VARCHAR(20) - 'draft' | 'available' | 'sold_out'
   - `seller_id`: FK → user.id
   - `is_active`: Boolean - Visibility control

3. **`ticket`** - Individual Seat Records
   - **Unique Constraint**: `(event_id, section, subsection, row_number, seat_number)`
   - `status`: VARCHAR(20) - 'available' | 'reserved' | 'sold'
   - `buyer_id`: FK → user.id (nullable)
   - `reserved_at`: TIMESTAMP (nullable)
   - `price`: INTEGER (cents)

4. **`booking`** - Order Records
   - `seat_positions`: ARRAY(String) - e.g., `['1-1', '1-2']`
   - `seat_selection_mode`: VARCHAR(20) - 'manual' | 'best_available'
   - `status`: VARCHAR(20) - 'processing' | 'pending_payment' | 'paid' | 'completed' | 'failed'
   - `total_price`: INTEGER (cents)
   - `created_at`, `updated_at`, `paid_at`: TIMESTAMP

5. **`booking_ticket`** - Many-to-Many Join Table
   - **Composite PK**: `(booking_id, ticket_id)`
   - Links bookings to tickets

## HTTP API Endpoints

See controller implementations:
- **Event API**: [event_ticketing_controller.py](../src/service/ticketing/driving_adapter/http_controller/event_ticketing_controller.py)
- **Booking API**: [booking_controller.py](../src/service/ticketing/driving_adapter/http_controller/booking_controller.py)
- **User API**: [user_controller.py](../src/service/ticketing/driving_adapter/http_controller/user_controller.py)

**Request/Response Schemas**: [schema/](../src/service/ticketing/driving_adapter/schema/)
- [event_schema.py](../src/service/ticketing/driving_adapter/schema/event_schema.py)
- [booking_schema.py](../src/service/ticketing/driving_adapter/schema/booking_schema.py)

## Key Design Decisions

1. **PostgreSQL for persistence**: ACID guarantees for booking/ticket consistency
2. **Kvrocks for seat state**: See [KVROCKS_SPEC.md](KVROCKS_SPEC.md) (400x storage reduction)
3. **Kafka for coordination**: See [KAFKA_SPEC.md](KAFKA_SPEC.md) (async seat reservation)
4. **Batch ticket insertion**: [event_ticketing_aggregate.py](../src/service/ticketing/domain/event_ticketing_aggregate.py) (~50x faster)
5. **CQRS pattern**: Separate read/write operations for scalability
6. **Aggregate pattern**: Ensures Event + Tickets consistency
7. **Role-based auth**: [role_auth_service.py](../src/service/ticketing/app/service/role_auth_service.py)
