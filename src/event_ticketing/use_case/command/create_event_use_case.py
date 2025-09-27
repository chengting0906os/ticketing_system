from typing import Dict, List

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.event_command_repo import EventCommandRepo
from src.event_ticketing.domain.event_entity import Event
from src.event_ticketing.domain.ticket_command_repo import TicketCommandRepo
from src.event_ticketing.domain.ticket_entity import Ticket, TicketStatus
from src.shared.config.db_setting import get_async_session
from src.shared.logging.loguru_io import Logger


class CreateEventUseCase:
    def __init__(self, event_repo: EventCommandRepo, ticket_repo: TicketCommandRepo):
        self.event_repo = event_repo
        self.ticket_repo = ticket_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
    ):
        from src.event_ticketing.infra.event_command_repo_impl import EventCommandRepoImpl
        from src.event_ticketing.infra.ticket_command_repo_impl import TicketCommandRepoImpl

        event_repo = EventCommandRepoImpl(session)
        ticket_repo = TicketCommandRepoImpl(session)
        return cls(event_repo=event_repo, ticket_repo=ticket_repo)

    @Logger.io
    async def create(
        self,
        *,
        name: str,
        description: str,
        seller_id: int,
        venue_name: str,
        seating_config: Dict,
        is_active: bool = True,
    ) -> Event:
        # Validate seating config and prices
        self._validate_seating_config(seating_config=seating_config)

        event = Event.create(
            name=name,
            description=description,
            seller_id=seller_id,
            venue_name=venue_name,
            seating_config=seating_config,
            is_active=is_active,
        )

        created_event = await self.event_repo.create(event=event)

        # Auto-create tickets based on seating configuration
        if created_event.id is not None:
            tickets = self._generate_tickets_from_seating_config(
                event_id=created_event.id, seating_config=seating_config
            )
            await self.ticket_repo.create_batch(tickets=tickets)

        return created_event

    def _validate_seating_config(self, *, seating_config: Dict) -> None:
        if not isinstance(seating_config, dict) or 'sections' not in seating_config:
            raise ValueError('Invalid seating configuration: must contain sections')

        sections = seating_config.get('sections', [])
        if not isinstance(sections, list) or len(sections) == 0:
            raise ValueError('Invalid seating configuration: sections must be a non-empty list')

        for section in sections:
            if not isinstance(section, dict):
                raise ValueError('Invalid seating configuration: each section must be a dictionary')

            # Check required fields
            required_fields = ['name', 'price', 'subsections']
            for field in required_fields:
                if field not in section:
                    raise ValueError(
                        f'Invalid seating configuration: section missing required field "{field}"'
                    )

            # Validate price
            price = section.get('price')
            if not isinstance(price, (int, float)) or price < 0:
                raise ValueError('Ticket price must over 0')

            # Validate subsections
            subsections = section.get('subsections', [])
            if not isinstance(subsections, list) or len(subsections) == 0:
                raise ValueError(
                    'Invalid seating configuration: each section must have subsections'
                )

            for subsection in subsections:
                if not isinstance(subsection, dict):
                    raise ValueError(
                        'Invalid seating configuration: each subsection must be a dictionary'
                    )

                required_subsection_fields = ['number', 'rows', 'seats_per_row']
                for field in required_subsection_fields:
                    if field not in subsection:
                        raise ValueError(
                            f'Invalid seating configuration: subsection missing required field "{field}"'
                        )

                # Validate numeric fields
                for field in ['number', 'rows', 'seats_per_row']:
                    value = subsection.get(field)
                    if not isinstance(value, int) or value <= 0:
                        raise ValueError(
                            f'Invalid seating configuration: {field} must be a positive integer'
                        )

    async def _generate_tickets_from_seating_config(
        self, *, event_id: int, seating_config: Dict
    ) -> List[Ticket]:
        """
        Generate tickets based on seating configuration.

        同時在 PostgreSQL 和 RocksDB 中初始化座位資料：
        - PostgreSQL: 存儲票據實體（用於查詢和報表）
        - RocksDB: 存儲座位狀態（用於高性能預訂）
        """
        tickets = []
        sections = seating_config.get('sections', [])

        # 導入 RocksDB 事件發送功能
        from datetime import datetime

        from src.shared.event_bus.unified_mq_publisher import publish_domain_event

        Logger.base.info(
            f'🏗️ [CREATE_EVENT] Initializing seats for event {event_id} in both PostgreSQL and RocksDB'
        )

        for section in sections:
            section_name = section['name']
            section_price = int(section['price'])
            subsections = section['subsections']

            for subsection in subsections:
                subsection_number = subsection['number']
                rows = subsection['rows']
                seats_per_row = subsection['seats_per_row']

                # Generate tickets for each seat
                for row in range(1, rows + 1):
                    for seat in range(1, seats_per_row + 1):
                        # 1) 創建 PostgreSQL 票據實體
                        ticket = Ticket(
                            event_id=event_id,
                            section=section_name,
                            subsection=subsection_number,
                            row=row,
                            seat=seat,
                            price=section_price,
                            status=TicketStatus.AVAILABLE,
                        )
                        tickets.append(ticket)

                        # 2) 發送座位初始化命令到 RocksDB
                        seat_id = f'{section_name}-{subsection_number}-{row}-{seat}'

                        try:
                            # 創建座位初始化事件（使用原始數據結構）
                            init_event = {
                                'event_type': 'SeatInitialization',
                                'aggregate_id': event_id,
                                'data': {
                                    'action': 'INITIALIZE',
                                    'seat_id': seat_id,
                                    'event_id': event_id,
                                    'price': section_price,
                                    'section': section_name,
                                    'subsection': subsection_number,
                                    'row': row,
                                    'seat': seat,
                                },
                                'occurred_at': datetime.now().isoformat(),
                            }

                            # 發送初始化命令到 RocksDB processor
                            await publish_domain_event(
                                event=init_event, topic='seat-commands', partition_key=seat_id
                            )

                        except Exception as e:
                            Logger.base.warning(
                                f'⚠️ [CREATE_EVENT] Failed to initialize seat {seat_id} in RocksDB: {e}'
                            )
                            # 繼續處理其他座位，不因單個座位失敗而中斷

        Logger.base.info(
            f'✅ [CREATE_EVENT] Generated {len(tickets)} tickets for event {event_id}, '
            f'sent initialization commands to RocksDB'
        )
        return tickets
