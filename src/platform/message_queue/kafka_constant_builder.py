from uuid import UUID


class ServiceNames:
    """Service name constants."""

    TICKETING_SERVICE = 'ticketing-service'  # Combines booking and event_ticketing.
    SEAT_RESERVATION_SERVICE = 'seat-reservation-service'


class KafkaTopicBuilder:
    """
    Unified Kafka topic naming builder.

    Format: event-id-{event_id}______{action}______{from_service}___to___{to_service}
    """

    # ====== To Seat Reservation Service =======
    @staticmethod
    def ticket_reserving_request_to_reserved_in_kvrocks(*, event_id: UUID) -> str:
        return f'event-id-{event_id}______ticket-reserving-request-in-kvrocks______{ServiceNames.TICKETING_SERVICE}___to___{ServiceNames.SEAT_RESERVATION_SERVICE}'

    @staticmethod
    def release_ticket_status_to_available_in_kvrocks(*, event_id: UUID) -> str:
        return f'event-id-{event_id}______release-ticket-status-to-available-in-kvrocks______{ServiceNames.TICKETING_SERVICE}___to___{ServiceNames.SEAT_RESERVATION_SERVICE}'

    @staticmethod
    def finalize_ticket_status_to_paid_in_kvrocks(*, event_id: UUID) -> str:
        return f'event-id-{event_id}______finalize-ticket-status-to-paid-in-kvrocks______{ServiceNames.TICKETING_SERVICE}___to___{ServiceNames.SEAT_RESERVATION_SERVICE}'

    # ====== To Ticketing Service (includes Booking + Event Ticketing) =======
    # NOTIFICATION PATTERN: These events represent completed actions, not commands
    # The database writes are already completed by the sender before publishing

    @staticmethod
    def seats_reserved_notification(*, event_id: UUID) -> str:
        """
        NOTIFICATION: Seat Reservation Service successfully reserved seats (PAST TENSE).

        What already happened (atomic ScyllaDB batch write):
        - Ticket status → RESERVED
        - Booking status → PENDING_PAYMENT
        - Seat state → locked

        Listeners can react by:
        - Sending confirmation emails
        - Updating caches
        - Triggering payment reminders
        - Recording analytics
        """
        return f'event-id-{event_id}______seats-reserved-notification______{ServiceNames.SEAT_RESERVATION_SERVICE}___to___{ServiceNames.TICKETING_SERVICE}'

    @staticmethod
    def booking_failed_notification(*, event_id: UUID) -> str:
        """
        NOTIFICATION: Seat Reservation Service failed to complete booking (PAST TENSE).

        What already happened:
        - Validation failed or timeout occurred
        - Booking status → FAILED
        - Seats released back to available pool

        Listeners can react by:
        - Notifying user of failure
        - Logging error metrics
        - Triggering retry logic if applicable
        """
        return f'event-id-{event_id}______booking-failed-notification______{ServiceNames.SEAT_RESERVATION_SERVICE}___to___{ServiceNames.TICKETING_SERVICE}'

    @staticmethod
    def ticketing_dlq(*, event_id: UUID) -> str:
        """Dead Letter Queue for ticketing service unrecoverable errors"""
        return f'event-id-{event_id}______ticketing-dlq______{ServiceNames.TICKETING_SERVICE}'

    @staticmethod
    def seat_reservation_dlq(*, event_id: UUID) -> str:
        """Dead Letter Queue for seat reservation service unrecoverable errors"""
        return f'event-id-{event_id}______seat-reservation-dlq______{ServiceNames.SEAT_RESERVATION_SERVICE}'

    @staticmethod
    def get_all_topics(*, event_id: UUID) -> list[str]:
        return [
            # To Seat Reservation Service (Commands)
            KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(event_id=event_id),
            KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(event_id=event_id),
            KafkaTopicBuilder.finalize_ticket_status_to_paid_in_kvrocks(event_id=event_id),
            # To Ticketing Service (Notifications)
            KafkaTopicBuilder.seats_reserved_notification(event_id=event_id),
            KafkaTopicBuilder.booking_failed_notification(event_id=event_id),
            # Dead Letter Queues
            KafkaTopicBuilder.ticketing_dlq(event_id=event_id),
            KafkaTopicBuilder.seat_reservation_dlq(event_id=event_id),
        ]


class KafkaConsumerGroupBuilder:
    """
    Unified Kafka consumer group naming builder.

    Format: event-id-{event_id}_____{service_name}-{event_id}
    """

    @staticmethod
    def ticketing_service(*, event_id: UUID) -> str:
        """Ticketing Service (combines booking + event_ticketing)."""
        return f'event-id-{event_id}_____{ServiceNames.TICKETING_SERVICE}--{event_id}'

    @staticmethod
    def seat_reservation_service(*, event_id: UUID) -> str:
        return f'event-id-{event_id}_____{ServiceNames.SEAT_RESERVATION_SERVICE}--{event_id}'

    @staticmethod
    def get_all_consumer_groups(*, event_id: UUID) -> list[str]:
        """Retrieve all consumer groups (Ticketing + Seat Reservation)."""
        return [
            KafkaConsumerGroupBuilder.ticketing_service(event_id=event_id),
            KafkaConsumerGroupBuilder.seat_reservation_service(event_id=event_id),
        ]


class KafkaProducerTransactionalIdBuilder:
    """
    Unified Kafka producer transactional ID naming builder.

    Transactional IDs are the core of Kafka exactly-once semantics:
    - Ensure producer idempotency (prevent duplicate writes)
    - Every producer instance must have a unique transactional.id
    - Format: {service_name}-producer-event-{event_id}-instance-{instance_id}

    Environment Variables:
    - KAFKA_PRODUCER_INSTANCE_ID: Producer instance identifier (default: "1")
    """

    @staticmethod
    def ticketing_service(*, event_id: UUID, instance_id: str) -> str:
        """Ticketing Service Producer Transactional ID"""
        return f'{ServiceNames.TICKETING_SERVICE}-producer-event-{event_id}-instance-{instance_id}'

    @staticmethod
    def seat_reservation_service(*, event_id: UUID, instance_id: str) -> str:
        """Seat Reservation Service Producer Transactional ID"""
        return f'{ServiceNames.SEAT_RESERVATION_SERVICE}-producer-event-{event_id}-instance-{instance_id}'


class PartitionKeyBuilder:
    """
    Unified partition key naming builder.

    Format: event-{event_id}-section-{section}-partition-{partition_number}
    """

    @staticmethod
    def section_based(*, event_id: UUID, section: str, partition_number: int = 0) -> str:
        return f'event-{event_id}-section-{section}-partition-{partition_number}'

    @staticmethod
    def booking_based(*, event_id: UUID) -> str:
        return f'event-{event_id}'

    @staticmethod
    def booking_with_id(*, event_id: UUID, booking_id: UUID) -> str:
        return f'event-{event_id}-booking-{booking_id}'

    @staticmethod
    def seat_based(*, event_id: UUID, section: str, partition_number: int = 0) -> str:
        return PartitionKeyBuilder.section_based(
            event_id=event_id, section=section, partition_number=partition_number
        )
