class ServiceNames:
    """Service name constants"""

    TICKETING_SERVICE = 'ticketing-service'  # Integrates booking + event_ticketing
    RESERVATION_SERVICE = 'reservation-service'


class KafkaTopicBuilder:
    """
    Kafka Topic Naming Unified Builder

    Format: event-id-{event_id}______{action}______{from_service}___to___{to_service}
    """

    # ====== To Seat Reservation Service =======
    @staticmethod
    def ticket_reserving_request_to_reserved_in_kvrocks(*, event_id: int) -> str:
        return f'event-id-{event_id}______ticket-reserving-request-in-kvrocks______{ServiceNames.TICKETING_SERVICE}___to___{ServiceNames.RESERVATION_SERVICE}'

    @staticmethod
    def release_ticket_status_to_available_in_kvrocks(*, event_id: int) -> str:
        return f'event-id-{event_id}______release-ticket-status-to-available-in-kvrocks______{ServiceNames.TICKETING_SERVICE}___to___{ServiceNames.RESERVATION_SERVICE}'

    @staticmethod
    def finalize_ticket_status_to_paid_in_kvrocks(*, event_id: int) -> str:
        return f'event-id-{event_id}______finalize-ticket-status-to-paid-in-kvrocks______{ServiceNames.TICKETING_SERVICE}___to___{ServiceNames.RESERVATION_SERVICE}'

    # ====== To Ticketing Service (includes Booking + Event Ticketing) =======

    @staticmethod
    def update_booking_status_to_pending_payment_and_ticket_status_to_reserved_in_postgresql(
        *, event_id: int
    ) -> str:
        """After successful seat reservation, update both Booking and Ticket status (atomic operation)"""
        return f'event-id-{event_id}______update-booking-status-to-pending-payment-and-ticket-status-to-reserved-in-postgresql______{ServiceNames.RESERVATION_SERVICE}___to___{ServiceNames.TICKETING_SERVICE}'

    @staticmethod
    def update_booking_status_to_failed(*, event_id: int) -> str:
        return f'event-id-{event_id}______update-booking-status-to-failed______{ServiceNames.RESERVATION_SERVICE}___to___{ServiceNames.TICKETING_SERVICE}'

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
            # To Seat Reservation Service
            KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(event_id=event_id),
            KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(event_id=event_id),
            KafkaTopicBuilder.finalize_ticket_status_to_paid_in_kvrocks(event_id=event_id),
            # To Ticketing Service
            KafkaTopicBuilder.update_booking_status_to_pending_payment_and_ticket_status_to_reserved_in_postgresql(
                event_id=event_id
            ),
            KafkaTopicBuilder.update_booking_status_to_failed(event_id=event_id),
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
        """Ticketing Service (integrates booking + event_ticketing)"""
        return f'event-id-{event_id}_____{ServiceNames.TICKETING_SERVICE}--{event_id}'

    @staticmethod
    def reservation_service(*, event_id: int) -> str:
        return f'event-id-{event_id}_____{ServiceNames.RESERVATION_SERVICE}--{event_id}'

    @staticmethod
    def get_all_consumer_groups(*, event_id: int) -> list[str]:
        """Get all consumer groups (Ticketing + Seat Reservation)"""
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
        """Seat Reservation Service Producer Transactional ID"""
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
