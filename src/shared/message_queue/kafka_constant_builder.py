class ServiceNames:
    """服務名稱常數"""

    BOOKING_SERVICE = 'booking-service'
    SEAT_RESERVATION_SERVICE = 'seat-reservation-service'
    EVENT_TICKETING_SERVICE = 'event-ticketing-service'


class KafkaTopicBuilder:
    """
    Kafka Topic 命名統一建構器

    使用格式: event-id-{event_id}______{action}______{from_service}___to___{to_service}
    """

    # ====== To Seat Reservation Service =======
    @staticmethod
    def ticket_reserving_request_to_reserved_in_rocksdb(*, event_id: int) -> str:
        return f'event-id-{event_id}______ticket-reserving-request-in-rocksdb______{ServiceNames.BOOKING_SERVICE}___to___{ServiceNames.SEAT_RESERVATION_SERVICE}'

    @staticmethod
    def release_ticket_status_to_available_in_rocksdb(*, event_id: int) -> str:
        return f'event-id-{event_id}______release-ticket-status-to-available-in-rocksdb______{ServiceNames.EVENT_TICKETING_SERVICE}___to___{ServiceNames.SEAT_RESERVATION_SERVICE}'

    @staticmethod
    def finalize_ticket_status_to_paid_in_rocksdb(*, event_id: int) -> str:
        return f'event-id-{event_id}______finalize-ticket-status-to-paid-in-rocksdb______{ServiceNames.EVENT_TICKETING_SERVICE}___to___{ServiceNames.SEAT_RESERVATION_SERVICE}'

    @staticmethod
    def seat_initialization_command_in_rocksdb(*, event_id: int) -> str:
        return f'event-id-{event_id}______seat-initialization-command-in-rocksdb______{ServiceNames.EVENT_TICKETING_SERVICE}___to___{ServiceNames.SEAT_RESERVATION_SERVICE}'

    # ====== To Event Ticketing Service =======

    @staticmethod
    def update_ticket_status_to_reserved_in_postgresql(*, event_id: int) -> str:
        return f'event-id-{event_id}______update-ticket-status-to-reserved-in-postgresql______{ServiceNames.SEAT_RESERVATION_SERVICE}___to___{ServiceNames.EVENT_TICKETING_SERVICE}'

    @staticmethod
    def update_ticket_status_to_paid_in_postgresql(*, event_id: int) -> str:
        return f'event-id-{event_id}______update-ticket-status-to-paid-in-postgresql______{ServiceNames.BOOKING_SERVICE}___to___{ServiceNames.EVENT_TICKETING_SERVICE}'

    @staticmethod
    def update_ticket_status_to_available_in_rocksdb(*, event_id: int) -> str:
        return f'event-id-{event_id}______update-ticket-status-to-available-in-postgresql______{ServiceNames.BOOKING_SERVICE}___to___{ServiceNames.EVENT_TICKETING_SERVICE}'

    # ====== To Booking Service =======
    @staticmethod
    def update_booking_status_to_pending_payment(*, event_id: int) -> str:
        return f'event-id-{event_id}______update-booking-status-to-pending-payment______{ServiceNames.SEAT_RESERVATION_SERVICE}___to___{ServiceNames.BOOKING_SERVICE}'

    @staticmethod
    def update_booking_status_to_failed(*, event_id: int) -> str:
        return f'event-id-{event_id}______update-booking-status-to-failed______{ServiceNames.SEAT_RESERVATION_SERVICE}___to___{ServiceNames.BOOKING_SERVICE}'

    @staticmethod
    def get_all_topics(*, event_id: int) -> list[str]:
        return [
            KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_rocksdb(event_id=event_id),
            KafkaTopicBuilder.update_ticket_status_to_reserved_in_postgresql(event_id=event_id),
            KafkaTopicBuilder.update_booking_status_to_pending_payment(event_id=event_id),
            KafkaTopicBuilder.update_booking_status_to_failed(event_id=event_id),
            KafkaTopicBuilder.update_ticket_status_to_paid_in_postgresql(event_id=event_id),
            KafkaTopicBuilder.update_ticket_status_to_available_in_rocksdb(event_id=event_id),
            KafkaTopicBuilder.release_ticket_status_to_available_in_rocksdb(event_id=event_id),
            KafkaTopicBuilder.finalize_ticket_status_to_paid_in_rocksdb(event_id=event_id),
            KafkaTopicBuilder.seat_initialization_command_in_rocksdb(event_id=event_id),
        ]


class KafkaConsumerGroupBuilder:
    """
    Kafka Consumer Group 命名統一建構器

    使用格式: event-id-{event_id}_____{service_name}-{event_id}
    """

    @staticmethod
    def booking_service(*, event_id: int) -> str:
        return f'event-id-{event_id}_____{ServiceNames.BOOKING_SERVICE}--{event_id}'

    @staticmethod
    def seat_reservation_service(*, event_id: int) -> str:
        return f'event-id-{event_id}_____{ServiceNames.SEAT_RESERVATION_SERVICE}--{event_id}'

    @staticmethod
    def event_ticketing_service(*, event_id: int) -> str:
        return f'event-id-{event_id}_____{ServiceNames.EVENT_TICKETING_SERVICE}--{event_id}'

    @staticmethod
    def get_all_consumer_groups(*, event_id: int) -> list[str]:
        """獲取 1-2-1 架構的所有 consumer groups"""
        return [
            KafkaConsumerGroupBuilder.booking_service(event_id=event_id),
            KafkaConsumerGroupBuilder.seat_reservation_service(event_id=event_id),
            KafkaConsumerGroupBuilder.event_ticketing_service(event_id=event_id),
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
