"""
https://python-dependency-injector.ets-labs.org/index.html
https://python-dependency-injector.ets-labs.org/examples/fastapi-sqlalchemy.html
"""

from dependency_injector import containers, providers

from src.booking.driven_adapter.booking_command_repo_impl import BookingCommandRepoImpl
from src.booking.driven_adapter.booking_query_repo_impl import BookingQueryRepoImpl
from src.event_ticketing.app.command.reserve_tickets_use_case import ReserveTicketsUseCase
from src.event_ticketing.driven_adapter.event_ticketing_command_repo_impl import (
    EventTicketingCommandRepoImpl,
)
from src.event_ticketing.driven_adapter.event_ticketing_query_repo_impl import (
    EventTicketingQueryRepoImpl,
)
from src.platform.config.core_setting import Settings
from src.platform.config.db_setting import Database
from src.platform.message_queue.kafka_config_service import KafkaConfigService
from src.platform.message_queue.section_based_partition_strategy import (
    SectionBasedPartitionStrategy,
)
from src.seat_reservation.app.command.finalize_seat_payment_use_case import (
    FinalizeSeatPaymentUseCase,
)
from src.seat_reservation.app.command.initialize_seat_use_case import InitializeSeatUseCase
from src.seat_reservation.app.command.release_seat_use_case import ReleaseSeatUseCase
from src.seat_reservation.app.command.reserve_seats_use_case import ReserveSeatsUseCase
from src.seat_reservation.app.query.get_section_seats_detail_use_case import (
    GetSectionSeatsDetailUseCase,
)
from src.seat_reservation.domain.seat_selection_domain import SeatSelectionDomain
from src.seat_reservation.driven_adapter.seat_reservation_mq_publisher import (
    SeatReservationEventPublisher,
)
from src.seat_reservation.driven_adapter.seat_state_handler_impl import SeatStateHandlerImpl
from src.shared_kernel.user.app.auth_service import AuthService
from src.shared_kernel.user.driven_adapter.user_command_repo_impl import UserCommandRepoImpl
from src.shared_kernel.user.driven_adapter.user_query_repo_impl import UserQueryRepoImpl
from src.shared_kernel.user.driven_adapter.user_repo_impl import UserRepoImpl


class Container(containers.DeclarativeContainer):
    # Configuration
    config_service = providers.Singleton(Settings)

    # Database
    database = providers.Singleton(Database, db_url=config_service.provided.DATABASE_URL_ASYNC)

    # Infrastructure services
    kafka_service = providers.Singleton(KafkaConfigService)
    partition_strategy = providers.Singleton(SectionBasedPartitionStrategy)

    # Repositories - now properly managed with session factory
    booking_command_repo = providers.Factory(
        BookingCommandRepoImpl, session_factory=database.provided.session
    )
    booking_query_repo = providers.Factory(
        BookingQueryRepoImpl, session_factory=database.provided.session
    )
    event_ticketing_command_repo = providers.Factory(
        EventTicketingCommandRepoImpl, session_factory=database.provided.session
    )
    event_ticketing_query_repo = providers.Factory(
        EventTicketingQueryRepoImpl, session_factory=database.provided.session
    )
    user_repo = providers.Factory(UserRepoImpl, session_factory=database.provided.session)
    user_command_repo = providers.Factory(
        UserCommandRepoImpl, session_factory=database.provided.session
    )
    user_query_repo = providers.Factory(
        UserQueryRepoImpl, session_factory=database.provided.session
    )

    # Auth service
    auth_service = providers.Singleton(AuthService)

    # Seat Reservation Infrastructure
    seat_reservation_mq_publisher = providers.Factory(SeatReservationEventPublisher)

    # Seat Reservation Domain and Use Cases
    seat_selection_domain = providers.Factory(SeatSelectionDomain)
    seat_state_handler = providers.Factory(SeatStateHandlerImpl)
    reserve_seats_use_case = providers.Factory(
        ReserveSeatsUseCase,
        seat_selection_domain=seat_selection_domain,
        seat_state_handler=seat_state_handler,
        mq_publisher=seat_reservation_mq_publisher,
    )
    initialize_seat_use_case = providers.Factory(
        InitializeSeatUseCase,
        seat_state_handler=seat_state_handler,
    )
    release_seat_use_case = providers.Factory(
        ReleaseSeatUseCase,
        seat_state_handler=seat_state_handler,
    )
    finalize_seat_payment_use_case = providers.Factory(
        FinalizeSeatPaymentUseCase,
        seat_state_handler=seat_state_handler,
    )
    get_section_seats_detail_use_case = providers.Factory(
        GetSectionSeatsDetailUseCase,
        session=providers.Dependency(),
    )

    # Event Ticketing Use Cases
    reserve_tickets_use_case = providers.Factory(
        ReserveTicketsUseCase,
        event_ticketing_command_repo=event_ticketing_command_repo,
        event_ticketing_query_repo=event_ticketing_query_repo,
    )


container = Container()


def setup():
    container.kafka_service()
    container.config_service()
    container.partition_strategy()


def cleanup():
    container.reset_singletons()
