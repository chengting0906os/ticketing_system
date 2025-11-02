# Kafka Event-Driven Messaging Specification

> **📁 Related Files**: [kafka_config_service.py](../src/platform/message_queue/kafka_config_service.py) | [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py) | [section_based_partition_strategy.py](../src/platform/message_queue/section_based_partition_strategy.py) | [docker-compose.yml](../docker-compose.yml)

## Quick Reference

**Cluster**: See [docker-compose.yml](../docker-compose.yml)
**Config**: See [core_setting.py](../src/platform/config/core_setting.py)
**Management**: Use `make c-start`, `make c-status`, `make c-tail`, `make c-stop`

## Topic Naming Convention

**Pattern**: `event-id-{event_id}______{action}______{from_service}___to___{to_service}`

**Builders**: See [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py)

| Builder Method | Example Topic Name |
|----------------|-------------------|
| `reserve_seats__ticketing_to_seat_reservation(1)` | `event-id-1______reserve-seats______ticketing-service___to___seat-reservation-service` |
| `seat_reserved__seat_reservation_to_ticketing(1)` | `event-id-1______seat-reserved______seat-reservation-service___to___ticketing-service` |
| `seat_reservation_failed__seat_reservation_to_ticketing(1)` | `event-id-1______seat-reservation-failed______seat-reservation-service___to___ticketing-service` |

**Get all topics**: `KafkaTopicBuilder.get_all_topics(event_id)`

## Consumer Groups

**Pattern**: `event-id-{event_id}_____{service_name}--{event_id}`

| Builder Method | Example Consumer Group |
|----------------|----------------------|
| `ticketing_service(1)` | `event-id-1_____ticketing-service--1` |
| `seat_reservation_service(1)` | `event-id-1_____seat-reservation-service--1` |

## Partition Strategy

**Subsection-Based Partitioning** (100 partitions total, 1 per subsection)

| Subsection | Partition Calculation | Example |
|------------|----------------------|---------|
| A-1 | `section_index * 10 + (subsection - 1)` | A-1 → 0×10+0 = 0 |
| A-2 | Same formula | A-2 → 0×10+1 = 1 |
| A-10 | Same formula | A-10 → 0×10+9 = 9 |
| B-1 | Same formula | B-1 → 1×10+0 = 10 |
| J-10 | Same formula | J-10 → 9×10+9 = 99 |

**Mapping**: Each subsection (A-1, A-2, ..., J-10) gets its own partition (0-99)

**Partition Key Builders**: See [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py)

```python
# Subsection-based (for seat operations)
partition = strategy.get_partition_for_subsection(section='A', subsection=1, event_id=1)
# A-1 → partition 0, A-2 → partition 1, B-1 → partition 10
section_id = f'{section}-{subsection}'  # e.g., 'A-1'
key = PartitionKeyBuilder.section_based(event_id, section_id, partition)
# Result: "event-1-section-A-1-partition-0"

# Booking-based (for booking operations)
key = PartitionKeyBuilder.booking_with_id(event_id, booking_id)
# Result: "event-1-booking-01234567-89ab-cdef-0123-456789abcdef"
```

**Why Subsection-Based?**

- Same subsection → same partition → locality optimization
- Kvrocks cache hit rate higher (all seats in A-1 cached together)
- Atomic operations within subsection (no cross-partition coordination)

## Environment Variables

```bash
EVENT_ID=1
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_CONSUMER_INSTANCE_ID=consumer-hostname-pid
KAFKA_PRODUCER_INSTANCE_ID=producer-pid
```

## Topic Lifecycle Management

### Create Topics (Automatic)

```python
# In setup
from src.platform.message_queue.kafka_config_service import setup_event_infrastructure

await setup_event_infrastructure(event_id=1)
# Creates all topics for event with 10 partitions, replication factor 3
```

### List Topics

```bash
docker exec kafka1 kafka-topics --bootstrap-server kafka1:29092 --list
```

### Reset Topics (Cleanup)

```bash
# Delete all topics except event-id-1*
uv run python script/reset_kafka.py
```

## Consumer Management

### Docker Compose

```bash
# Start all consumers (4 ticketing + 4 seat-reservation)
make c-start

# Check consumer status
make c-status

# View consumer logs
make c-tail

# Stop all consumers
make c-stop
```

### Manual Consumer Commands

```bash
# View consumer group details
docker exec kafka1 kafka-consumer-groups \
  --bootstrap-server kafka1:29092 \
  --group event-id-1_____seat-reservation-service--1 \
  --describe

# List all consumer groups
docker exec kafka1 kafka-consumer-groups \
  --bootstrap-server kafka1:29092 \
  --list
```

## Message Flow Example

```text
┌─────────────────┐    reserve-seats     ┌──────────────────────┐
│ Ticketing       ├───────────────────────>                      │
│ Service         │                        │ Seat Reservation    │
│ (Producer)      │    seat-reserved      │ Service              │
│                 <───────────────────────┤ (Consumer/Producer)  │
└─────────────────┘                        └──────────────────────┘
      ^                                              │
      │         seat-reservation-failed             │
      └─────────────────────────────────────────────┘
```

**Partition Key**: Same `booking_id` → same partition → sequential processing → no race conditions

## Key Design Decisions

1. **Event-specific topics**: Isolated infrastructure per event (clean boundaries, easier cleanup)
2. **Section-based partitioning**: Locality-optimized for cache efficiency (same section → same partition)
3. **10 partitions per topic**: Balance between parallelism and overhead
4. **Replication factor 3**: Fault tolerance with 3-node cluster
5. **Consumer groups per service**: Independent scaling and failure isolation
6. **Partition key = booking_id**: Sequential processing guarantee (no concurrent updates)
