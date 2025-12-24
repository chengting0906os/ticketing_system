class ServiceNames:
    """Service name constants"""

    TICKETING_SERVICE = 'ticketing-service'  # HTTP API + availability check
    BOOKING_SERVICE = 'booking-service'  # Booking metadata management
    RESERVATION_SERVICE = 'reservation-service'  # Seat reservation + PostgreSQL writes


class KafkaTopicBuilder:
    """
    Kafka Topic Naming Unified Builder

    Format: event-id-{event_id}______{action}______{from_service}___to___{to_service}
    """

    # ====== To Reservation Service (unified topic for reserve/release) =======
    @staticmethod
    def ticket_command_request(*, event_id: int) -> str:
        """Unified topic for seat reservation commands (reserve/release).

        Uses action field in message to route:
        - action='reserve': Reserve seats (AVAILABLE → RESERVED)
        - action='release': Release seats (RESERVED → AVAILABLE)

        Same topic ensures ordering - no race condition between reserve/release.
        """
        return f'event-id-{event_id}______ticket-command-request______{ServiceNames.TICKETING_SERVICE}___to___{ServiceNames.RESERVATION_SERVICE}'

    # ====== Dead Letter Queues =======
    @staticmethod
    def reservation_dlq(*, event_id: int) -> str:
        """Dead Letter Queue for seat reservation service unrecoverable errors"""
        return (
            f'event-id-{event_id}______seat-reservation-dlq______{ServiceNames.RESERVATION_SERVICE}'
        )

    @staticmethod
    def get_all_topics(*, event_id: int) -> list[str]:
        return [
            KafkaTopicBuilder.ticket_command_request(event_id=event_id),
            KafkaTopicBuilder.reservation_dlq(event_id=event_id),
        ]


class KafkaConsumerGroupBuilder:
    """
    Kafka Consumer Group Naming Unified Builder

    Format: event-id-{event_id}_____{service_name}-{event_id}
    """

    @staticmethod
    def reservation_service(*, event_id: int) -> str:
        return f'event-id-{event_id}_____{ServiceNames.RESERVATION_SERVICE}--{event_id}'


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
        """Seat Reservation Service Producer Transactional ID"""
        return (
            f'{ServiceNames.RESERVATION_SERVICE}-producer-event-{event_id}-instance-{instance_id}'
        )
