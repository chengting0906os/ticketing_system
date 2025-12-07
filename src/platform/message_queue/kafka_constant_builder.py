class ServiceNames:
    """Service name constants"""

    TICKETING_SERVICE = 'ticketing-service'  # HTTP API + availability check
    RESERVATION_SERVICE = 'reservation-service'  # Seat reservation + KVRocks + PostgreSQL writes


class KafkaTopicBuilder:
    """
    Kafka Topic Naming Unified Builder

    Format: event-id-{event_id}______{action}______{from_service}___to___{to_service}
    """

    # ====== To Reservation Service (direct from Ticketing) =======
    @staticmethod
    def ticketing_to_reservation_reserve_seats(*, event_id: int) -> str:
        """Ticketing sends reservation request directly to Reservation Service"""
        return f'event-id-{event_id}______reserve-seats-request______{ServiceNames.TICKETING_SERVICE}___to___{ServiceNames.RESERVATION_SERVICE}'

    @staticmethod
    def ticket_release_seats(*, event_id: int) -> str:
        """Release reserved seats back to available"""
        return f'event-id-{event_id}______release-seats______{ServiceNames.TICKETING_SERVICE}___to___{ServiceNames.RESERVATION_SERVICE}'

    @staticmethod
    def ticket_reserved_to_paid(*, event_id: int) -> str:
        """Finalize payment - mark seats as sold"""
        return f'event-id-{event_id}______finalize-payment______{ServiceNames.TICKETING_SERVICE}___to___{ServiceNames.RESERVATION_SERVICE}'

    @staticmethod
    def ticketing_dlq(*, event_id: int) -> str:
        """Dead Letter Queue for ticketing service unrecoverable errors"""
        return f'event-id-{event_id}______ticketing-dlq______{ServiceNames.TICKETING_SERVICE}'

    @staticmethod
    def reservation_dlq(*, event_id: int) -> str:
        """Dead Letter Queue for seat reservation service unrecoverable errors"""
        return (
            f'event-id-{event_id}______seat-reservation-dlq______{ServiceNames.RESERVATION_SERVICE}'
        )

    @staticmethod
    def get_all_topics(*, event_id: int) -> list[str]:
        return [
            # Ticketing → Reservation (direct)
            KafkaTopicBuilder.ticketing_to_reservation_reserve_seats(event_id=event_id),
            KafkaTopicBuilder.ticket_release_seats(event_id=event_id),
            KafkaTopicBuilder.ticket_reserved_to_paid(event_id=event_id),
            # Dead Letter Queues
            KafkaTopicBuilder.ticketing_dlq(event_id=event_id),
            KafkaTopicBuilder.reservation_dlq(event_id=event_id),
        ]


class KafkaConsumerGroupBuilder:
    """
    Kafka Consumer Group Naming Unified Builder

    Format: event-id-{event_id}_____{service_name}-{event_id}
    """

    @staticmethod
    def ticketing_service(*, event_id: int) -> str:
        """Ticketing Service (HTTP API)"""
        return f'event-id-{event_id}_____{ServiceNames.TICKETING_SERVICE}--{event_id}'

    @staticmethod
    def reservation_service(*, event_id: int) -> str:
        """Reservation Service (KVRocks + PostgreSQL)"""
        return f'event-id-{event_id}_____{ServiceNames.RESERVATION_SERVICE}--{event_id}'

    @staticmethod
    def get_all_consumer_groups(*, event_id: int) -> list[str]:
        """Get all consumer groups (Ticketing + Reservation)"""
        return [
            KafkaConsumerGroupBuilder.ticketing_service(event_id=event_id),
            KafkaConsumerGroupBuilder.reservation_service(event_id=event_id),
        ]


class KafkaProducerTransactionalIdBuilder:
    """
    Kafka Producer Transactional ID Naming Unified Builder

    Transactional ID is the core of Kafka exactly-once semantics:
    - Ensures producer idempotency (prevents duplicate writes)
    - Each producer instance must have a unique transactional.id
    - Format: {service_name}-producer-event-{event_id}-instance-{instance_id}

    Environment Variables:
    - KAFKA_PRODUCER_INSTANCE_ID: Producer instance identifier (default: "1")
    """

    @staticmethod
    def ticketing_service(*, event_id: int, instance_id: str) -> str:
        """Ticketing Service Producer Transactional ID"""
        return f'{ServiceNames.TICKETING_SERVICE}-producer-event-{event_id}-instance-{instance_id}'

    @staticmethod
    def reservation_service(*, event_id: int, instance_id: str) -> str:
        """Reservation Service Producer Transactional ID"""
        return (
            f'{ServiceNames.RESERVATION_SERVICE}-producer-event-{event_id}-instance-{instance_id}'
        )


class PartitionKeyBuilder:
    """
    Partition Key Naming Unified Builder

    Format: event-{event_id}-section-{section}-partition-{partition_number}
    """

    @staticmethod
    def section_based(*, event_id: int, section: str, partition_number: int = 0) -> str:
        return f'event-{event_id}-section-{section}-partition-{partition_number}'

    @staticmethod
    def booking_based(*, event_id: int) -> str:
        return f'event-{event_id}'

    @staticmethod
    def booking_with_id(*, event_id: int, booking_id: int) -> str:
        return f'event-{event_id}-booking-{booking_id}'

    @staticmethod
    def seat_based(*, event_id: int, section: str, partition_number: int = 0) -> str:
        return PartitionKeyBuilder.section_based(
            event_id=event_id, section=section, partition_number=partition_number
        )
