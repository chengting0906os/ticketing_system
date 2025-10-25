# Kafka Configuration Specification

> **📁 Related Files**: [kafka_config_service.py](../src/platform/message_queue/kafka_config_service.py) | [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py) | [subsection_based_partition_strategy.py](../src/platform/message_queue/subsection_based_partition_strategy.py) | [docker-compose.yml](../docker-compose.yml) | [reset_kafka.py](../script/reset_kafka.py)

## Cluster Infrastructure

See [docker-compose.yml](../docker-compose.yml) for cluster setup

## Topic Naming Convention

See [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py):

- **Pattern**: `event-id-{event_id}______{action}______{from_service}___to___{to_service}`
- **Service Names**: `ServiceNames` class

### Topic Builders

See [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py):

- **Topic builders**: `KafkaTopicBuilder` class methods
- **Get all topics**: `KafkaTopicBuilder.get_all_topics(event_id)`

**Topic Configuration**: See [kafka_config_service.py](../src/platform/message_queue/kafka_config_service.py) for partition/replication settings

## Partition Strategy

See [subsection_based_partition_strategy.py](../src/platform/message_queue/subsection_based_partition_strategy.py):

**Mapping Logic**:

- Single-letter sections (A-J) → Alphabetical (A=0, B=1, ..., J=9)
- Multi-character sections → MD5 hash modulo 10

**Partition Key Builders**: See [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py) `PartitionKeyBuilder` class

- `section_based()` - Event + section + partition number
- `booking_based()` - Event only
- `booking_with_id()` - Event + booking ID

**Partition Key Generation**: See [subsection_based_partition_strategy.py](../src/platform/message_queue/subsection_based_partition_strategy.py)

```python
partition = get_partition_for_section(section, event_id)  # A → 0, B → 1
key = PartitionKeyBuilder.section_based(event_id, section, partition)
# Result: "event-1-section-A-partition-0"
```

**Load Distribution Analysis**: See [kafka_config_service.py](../src/platform/message_queue/kafka_config_service.py) `log_partition_distribution()`

## Consumer Groups

See [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py) `KafkaConsumerGroupBuilder` class:

**Naming Pattern**: `event-id-{event_id}_____{service_name}--{event_id}`

**Consumer Group Builders**:

- `ticketing_service(event_id)`
- `seat_reservation_service(event_id)`

**Consumer Configuration**: See [kafka_config_service.py](../src/platform/message_queue/kafka_config_service.py)

**Environment Variables**: See [kafka_config_service.py](../src/platform/message_queue/kafka_config_service.py)

```bash
EVENT_ID=1
CONSUMER_GROUP_ID=event-id-1_____seat-reservation-service--1
KAFKA_CONSUMER_INSTANCE_ID=1  # For multiple consumer instances
KAFKA_PRODUCER_INSTANCE_ID=producer-12345  # For producer transactional.id
PYTHONPATH=/path/to/project
```

**Startup**: See [kafka_config_service.py](../src/platform/message_queue/kafka_config_service.py)

```bash
uv run python -m src.service.seat_reservation.driving_adapter.seat_reservation_mq_consumer
```

## Topic Lifecycle Management

### Automatic Creation

See [kafka_config_service.py](../src/platform/message_queue/kafka_config_service.py) `setup_event_infrastructure()`:

- Creates all topics for an event
- Uses Docker exec to run `kafka-topics --create`
- Creates topics concurrently

### Cleanup

See [reset_kafka.py](../script/reset_kafka.py):

- **Protected**: `event-id-1*` topics
- **Deleted**: All other event topics
- **Verification**: Lists remaining topics

Commands:

```bash
# Reset all Kafka topics (except event-id-1)
uv run python script/reset_kafka.py

# List topics
docker exec kafka1 kafka-topics --bootstrap-server kafka1:29092 --list

# List consumer groups
docker exec kafka1 kafka-consumer-groups --bootstrap-server kafka1:29092 --list
```

## Monitoring

### Consumer Group Status

See [kafka_config_service.py](../src/platform/message_queue/kafka_config_service.py):

```bash
docker exec kafka1 kafka-consumer-groups \
  --bootstrap-server kafka1:29092 \
  --group event-id-1_____seat-reservation-service--1 \
  --describe
```

## Producer Performance (High Throughput)

> **📁 Related Files**: [event_publisher.py](../src/platform/message_queue/event_publisher.py) | [main.py](../src/service/ticketing/main.py)

**Target**: 10,000+ requests/sec with low latency

### Batching Configuration

See [event_publisher.py](../src/platform/message_queue/event_publisher.py) `_get_quix_app()`:

```python
producer_extra_config={
    # Batching (high throughput)
    'linger.ms': 50,                    # Accumulate for 50ms
    'batch.size': 524288,               # 512KB batch size
    'batch.num.messages': 1000,         # Or 1000 messages
    # Network optimization
    'compression.type': 'lz4',          # Fast compression
    'socket.send.buffer.bytes': 1048576, # 1MB send buffer

    # Reliability (exactly-once)
    'enable.idempotence': True,
    'acks': 'all',
}
```

### Non-blocking Publishing

See [event_publisher.py](../src/platform/message_queue/event_publisher.py) `publish_domain_event()`:

- **Default**: No flush (fire-and-forget, batched by background task)
- **Optional**: `force_flush=True` for critical events (e.g., payment)

```python
# General event (non-blocking, high throughput)
await publish_domain_event(
    event=BookingCreated(...),
    topic=topic,
    partition_key=key,
)

# Critical event (immediate flush)
await publish_domain_event(
    event=BookingPaid(...),
    topic=topic,
    partition_key=key,
    force_flush=True,  # Ensure immediate delivery
)
```

## Key Design Decisions

1. **Event-specific topics**: Isolated infrastructure per event (clean boundaries, easier cleanup)
2. **Section-based partitioning**: Locality-optimized for cache efficiency (see [subsection_based_partition_strategy.py](../src/platform/message_queue/subsection_based_partition_strategy.py))
3. **Batch publishing**: Non-blocking fire-and-forget with background flush for 10k+ TPS
4. **Exactly-once semantics**: Maintained via idempotence and transactions
5. **Cluster configuration**: See [docker-compose.yml](../docker-compose.yml) for deployment setup
