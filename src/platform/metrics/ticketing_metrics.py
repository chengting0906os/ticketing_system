from prometheus_client import Counter, Gauge, Histogram


class TicketingMetrics:
    """
    Ticketing System Core Metrics Collector

    Designed specifically for 50K tickets x 100 sections scenario
    Tracks Kafka consumer performance and seat reservation business metrics
    """

    def __init__(self):
        # ========== Kafka Consumer Metrics ==========
        self.kafka_messages_processed = Counter(
            'kafka_consumer_messages_processed_total',
            'Total processed messages',
            ['service', 'topic', 'partition', 'event_id'],
        )

        self.kafka_consumer_lag = Gauge(
            'kafka_consumer_lag_seconds',
            'Consumer lag in seconds',
            ['service', 'topic', 'partition', 'event_id'],
        )

        self.kafka_processing_duration = Histogram(
            'kafka_consumer_processing_duration_seconds',
            'Message processing duration',
            ['service', 'topic', 'event_id'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
        )

        self.kafka_consumer_errors = Counter(
            'kafka_consumer_errors_total',
            'Consumer processing errors',
            ['service', 'topic', 'error_type', 'event_id'],
        )

        # ========== Seat Reservation Business Metrics ==========
        self.seat_reservation_requests = Counter(
            'seat_reservation_requests_total',
            'Total seat reservation requests',
            ['event_id', 'section', 'mode', 'result'],  # mode: manual/best_available
        )

        self.seat_reservation_duration = Histogram(
            'seat_reservation_duration_seconds',
            'Seat reservation processing time',
            ['event_id', 'section', 'mode'],
            buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0],
        )

        self.seat_availability = Gauge(
            'seat_availability_ratio',
            'Available seats ratio per section',
            ['event_id', 'section', 'subsection'],
        )

        self.concurrent_bookings = Gauge(
            'concurrent_bookings_gauge', 'Active booking processes', ['event_id']
        )

        # ========== Kvrocks/Redis Operation Metrics ==========
        self.kvrocks_operations = Counter(
            'kvrocks_operations_total',
            'Total Kvrocks operations',
            ['operation', 'event_id', 'result'],  # operation: reserve/release/query
        )

        self.kvrocks_operation_duration = Histogram(
            'kvrocks_operation_duration_seconds',
            'Kvrocks operation duration',
            ['operation', 'event_id'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
        )

        # ========== System Health Metrics ==========
        self.service_uptime = Gauge(
            'service_uptime_seconds', 'Service uptime in seconds', ['service', 'instance_id']
        )

        self.database_connections_active = Gauge(
            'database_connections_active',
            'Active database connections',
            ['service', 'database_type'],  # postgresql/kvrocks
        )

    # ========== Helper Methods ==========

    def record_kafka_message_processed(
        self, *, service: str, topic: str, partition: str, event_id: int, processing_time: float
    ):
        self.kafka_messages_processed.labels(
            service=service, topic=topic, partition=partition, event_id=event_id
        ).inc()

        self.kafka_processing_duration.labels(
            service=service, topic=topic, event_id=event_id
        ).observe(processing_time)

    def record_kafka_error(self, *, service: str, topic: str, error_type: str, event_id: int):
        self.kafka_consumer_errors.labels(
            service=service, topic=topic, error_type=error_type, event_id=event_id
        ).inc()

    def record_seat_reservation(
        self, *, event_id: int, section: str, mode: str, result: str, duration: float
    ):
        self.seat_reservation_requests.labels(
            event_id=event_id, section=section, mode=mode, result=result
        ).inc()

        self.seat_reservation_duration.labels(
            event_id=event_id, section=section, mode=mode
        ).observe(duration)

    def update_seat_availability(
        self, *, event_id: int, section: str, subsection: str, ratio: float
    ):
        self.seat_availability.labels(
            event_id=event_id, section=section, subsection=subsection
        ).set(ratio)

    def record_kvrocks_operation(
        self, *, operation: str, event_id: int, result: str, duration: float
    ):
        self.kvrocks_operations.labels(operation=operation, event_id=event_id, result=result).inc()

        self.kvrocks_operation_duration.labels(operation=operation, event_id=event_id).observe(
            duration
        )


# Global metrics instance
metrics = TicketingMetrics()
