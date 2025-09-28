class KafkaTopicBuilder:
    """
    Kafka Topic 命名統一建構器

    使用格式: event-id-{event_id}::{action}:::::{from_service}>>>{to_service}
    """

    @staticmethod
    def ticket_reserve_request(*, event_id: int) -> str:
        return f'event-id-{event_id}::ticket-reserve-request:::::booking-service>>>seat-reservation-service'

    @staticmethod
    def update_ticket_status_to_reserved(*, event_id: int) -> str:
        return f'event-id-{event_id}::update-ticket-status-to-reserved:::::seat-reservation-service>>>event-ticketing-service'

    @staticmethod
    def update_booking_status_to_pending_payment(*, event_id: int) -> str:
        return f'event-id-{event_id}::update-booking-status-to-pending-payment:::::seat-reservation-service>>>booking-service'

    @staticmethod
    def update_booking_status_to_failed(*, event_id: int) -> str:
        return f'event-id-{event_id}::update-booking-status-to-failed:::::seat-reservation-service>>>booking-service'

    @staticmethod
    def update_ticket_status_to_paid(*, event_id: int) -> str:
        return f'event-id-{event_id}::update-ticket-status-to-paid:::::booking-service>>>event-ticketing-service'

    @staticmethod
    def update_ticket_status_to_available(*, event_id: int) -> str:
        return f'event-id-{event_id}::update-ticket-status-to-available:::::booking-service>>>event-ticketing-service'

    @staticmethod
    def release_ticket_to_available_by_rocksdb(*, event_id: int) -> str:
        return f'event-id-{event_id}::release-ticket-to-available-by-rocksdb:::::event-ticketing-service>>>seat-reservation-service'

    @staticmethod
    def finalize_ticket_to_paid_by_rocksdb(*, event_id: int) -> str:
        return f'event-id-{event_id}::finalize-ticket-to-paid-by-rocksdb:::::event-ticketing-service>>>seat-reservation-service'

    @staticmethod
    def get_all_topics(*, event_id: int) -> list[str]:
        return [
            KafkaTopicBuilder.ticket_reserve_request(event_id=event_id),
            KafkaTopicBuilder.update_ticket_status_to_reserved(event_id=event_id),
            KafkaTopicBuilder.update_booking_status_to_pending_payment(event_id=event_id),
            KafkaTopicBuilder.update_booking_status_to_failed(event_id=event_id),
            KafkaTopicBuilder.update_ticket_status_to_paid(event_id=event_id),
            KafkaTopicBuilder.update_ticket_status_to_available(event_id=event_id),
            KafkaTopicBuilder.release_ticket_to_available_by_rocksdb(event_id=event_id),
            KafkaTopicBuilder.finalize_ticket_to_paid_by_rocksdb(event_id=event_id),
        ]


class PartitionKeyBuilder:
    """
    Partition Key 命名統一建構器

    使用格式: event-{event_id}-section-{section}-partition-{partition_number}
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
