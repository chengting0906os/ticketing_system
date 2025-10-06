# Seat Reservation Service Specification

> **📂 Service Root**: [src/service/seat_reservation/](../src/service/seat_reservation/)
>
> **📁 Directory Structure**:
> ```
> seat_reservation/
> ├── driving_adapter/
> │   ├── seat_reservation_controller.py    # HTTP endpoints
> │   ├── seat_reservation_mq_consumer.py   # Kafka consumer
> │   └── seat_schema.py                    # Pydantic schemas
> ├── app/
> │   ├── command/                          # Write operations
> │   ├── query/                            # Read operations
> │   └── interface/                        # Port interfaces
> ├── domain/
> │   └── seat_selection_domain.py          # Selection strategies
> └── driven_adapter/
>     └── seat_state_handler_impl.py       # Kvrocks operations
> ```

## Architecture

See directory structure above for Hexagonal Architecture implementation.

**Key Components**:
- **Domain**: [seat_selection_domain.py](../src/service/seat_reservation/domain/seat_selection_domain.py) - Manual vs Best-Available strategies
- **State Handler**: [seat_state_handler_impl.py](../src/service/seat_reservation/driven_adapter/seat_state_handler_impl.py) - Kvrocks bitfield operations

## Data Storage

See [KVROCKS_SPEC.md](KVROCKS_SPEC.md) for complete data structure documentation.

**Quick Summary**:
- **Bitfield**: 2 bits per seat (0b00=available, 0b01=reserved, 0b10=sold)
- **Storage**: 25 bytes for 100 seats (400x reduction vs SQL)
- **Performance**: < 2ms for 500-seat read/write

## Use Cases

### Seat Reservation
- **Reserve**: [reserve_seats_use_case.py](../src/service/seat_reservation/app/command/reserve_seats_use_case.py)
- **Finalize**: [finalize_seat_payment_use_case.py](../src/service/seat_reservation/app/command/finalize_seat_payment_use_case.py)
- **Release**: [release_seat_use_case.py](../src/service/seat_reservation/app/command/release_seat_use_case.py)

### Seat Query
- **List Stats**: [list_all_subsection_status_use_case.py](../src/service/seat_reservation/app/query/list_all_subsection_status_use_case.py)
- **List Seats**: [list_section_seats_detail_use_case.py](../src/service/seat_reservation/app/query/list_section_seats_detail_use_case.py)

## Seat Selection Strategies

See [seat_selection_domain.py](../src/service/seat_reservation/domain/seat_selection_domain.py):
- **`ManualSeatSelection`** - Validates user-picked seats
- **`BestAvailableSelection`** - Finds optimal consecutive seats

## HTTP API Endpoints

See [seat_reservation_controller.py](../src/service/seat_reservation/driving_adapter/seat_reservation_controller.py)

**Schemas**: [seat_schema.py](../src/service/seat_reservation/driving_adapter/seat_schema.py)

## Kafka Integration

### MQ Consumer
See [seat_reservation_mq_consumer.py](../src/service/seat_reservation/driving_adapter/seat_reservation_mq_consumer.py)

### Topics
See [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py) `KafkaTopicBuilder` class for topic naming

See [KAFKA_SPEC.md](KAFKA_SPEC.md) for partition strategy and consumer group configuration.

## Key Design Decisions

1. **Kvrocks bitfield**: See [KVROCKS_SPEC.md](KVROCKS_SPEC.md) - 400x storage reduction, sub-millisecond reads
2. **Section-based partitioning**: See [KAFKA_SPEC.md](KAFKA_SPEC.md) - Cache locality optimization
3. **Strategy pattern**: [seat_selection_domain.py](../src/service/seat_reservation/domain/seat_selection_domain.py) - Pluggable seat selection
4. **Atomic operations**: [seat_state_handler_impl.py](../src/service/seat_reservation/driven_adapter/seat_state_handler_impl.py) - Kvrocks pipeline for consistency
5. **Best-available algorithm**: Front-row priority + consecutive grouping for UX
