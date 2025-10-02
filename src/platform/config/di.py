"""
https://python-dependency-injector.ets-labs.org/index.html
https://python-dependency-injector.ets-labs.org/examples/fastapi-sqlalchemy.html
"""

from dependency_injector import containers, providers

from src.booking.driven.booking_command_repo_impl import BookingCommandRepoImpl
from src.booking.driven.booking_query_repo_impl import BookingQueryRepoImpl
from src.event_ticketing.driven.event_ticketing_command_repo_impl import (
    EventTicketingCommandRepoImpl,
)
from src.event_ticketing.driven.event_ticketing_query_repo_impl import EventTicketingQueryRepoImpl
from src.event_ticketing.driving.event_ticketing_mq_gateway import EventTicketingMqGateway
from src.event_ticketing.use_case.command.reserve_tickets_use_case import ReserveTicketsUseCase
from src.platform.config.core_setting import Settings
from src.platform.config.db_setting import Database
from src.platform.message_queue.kafka_config_service import KafkaConfigService
from src.platform.message_queue.section_based_partition_strategy import (
    SectionBasedPartitionStrategy,
)
from src.seat_reservation.domain.seat_selection_domain import SeatSelectionDomain
from src.seat_reservation.driven.seat_state_handler_impl import SeatStateHandlerImpl
from src.seat_reservation.driven.seat_state_store import SeatStateStore
from src.seat_reservation.driving.seat_reservation_mq_gateway import SeatReservationGateway
from src.seat_reservation.use_case.reserve_seats_use_case import ReserveSeatsUseCase
from src.shared_kernel.user.infra.user_command_repo_impl import UserCommandRepoImpl
from src.shared_kernel.user.infra.user_query_repo_impl import UserQueryRepoImpl
from src.shared_kernel.user.infra.user_repo_impl import UserRepoImpl
from src.shared_kernel.user.use_case.auth_service import AuthService


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
    seat_state_store = providers.Singleton(SeatStateStore)

    # Seat Reservation Domain and Use Cases
    seat_selection_domain = providers.Factory(SeatSelectionDomain)
    seat_state_handler = providers.Factory(
        SeatStateHandlerImpl,
        seat_state_store=seat_state_store,
    )
    reserve_seats_use_case = providers.Factory(
        ReserveSeatsUseCase,
        seat_selection_domain=seat_selection_domain,
        seat_state_handler=seat_state_handler,
    )

    # Event Ticketing Use Cases
    reserve_tickets_use_case = providers.Factory(
        ReserveTicketsUseCase,
        event_ticketing_command_repo=event_ticketing_command_repo,
        event_ticketing_query_repo=event_ticketing_query_repo,
    )

    # Gateways
    seat_reservation_gateway = providers.Factory(
        SeatReservationGateway, reserve_seats_use_case=reserve_seats_use_case
    )

    event_ticketing_mq_gateway = providers.Factory(
        EventTicketingMqGateway, reserve_tickets_use_case=reserve_tickets_use_case
    )


container = Container()


def setup():
    container.kafka_service()
    container.config_service()
    container.partition_strategy()
    container.seat_state_store()


def cleanup():
    container.reset_singletons()
