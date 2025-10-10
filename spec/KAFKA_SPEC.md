# Kafka Configuration Specification

> **📁 Related Files**: [kafka_config_service.py](../src/platform/message_queue/kafka_config_service.py) | [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py) | [section_based_partition_strategy.py](../src/platform/message_queue/section_based_partition_strategy.py) | [docker-compose.yml](../docker-compose.yml) | [reset_kafka.py](../script/reset_kafka.py)

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

See [section_based_partition_strategy.py](../src/platform/message_queue/section_based_partition_strategy.py):

**Mapping Logic**:
- Single-letter sections (A-J) → Alphabetical (A=0, B=1, ..., J=9)
- Multi-character sections → MD5 hash modulo 10

**Partition Key Builders**: See [kafka_constant_builder.py](../src/platform/message_queue/kafka_constant_builder.py) `PartitionKeyBuilder` class
- `section_based()` - Event + section + partition number
- `booking_based()` - Event only
- `booking_with_id()` - Event + booking ID

**Partition Key Generation**: See [section_based_partition_strategy.py](../src/platform/message_queue/section_based_partition_strategy.py)
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

## Key Design Decisions

1. **Event-specific topics**: Isolated infrastructure per event (clean boundaries, easier cleanup)
2. **Section-based partitioning**: Locality-optimized for cache efficiency (see [section_based_partition_strategy.py](../src/platform/message_queue/section_based_partition_strategy.py))
3. **Cluster configuration**: See [docker-compose.yml](../docker-compose.yml) for deployment setup
