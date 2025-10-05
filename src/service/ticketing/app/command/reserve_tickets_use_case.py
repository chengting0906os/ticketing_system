"""
Reserve Tickets Use Case - 使用新的 EventTicketingAggregate

重構後的票務預訂業務邏輯：
- 使用 EventTicketingAggregate 作為聚合根
- 保證票務預訂的事務一致性
- 通過聚合根執行業務規則
- 增強的日誌記錄
"""

from typing import Any, Dict, List

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import EventTicketingAggregate
from src.service.ticketing.app.interface.i_event_ticketing_command_repo import (
    EventTicketingCommandRepo,
)
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import EventTicketingQueryRepo
from src.platform.exception.exceptions import DomainError, NotFoundError
from src.platform.logging.loguru_io import Logger


class ReserveTicketsUseCase:
    def __init__(
        self,
        event_ticketing_command_repo: EventTicketingCommandRepo,
        event_ticketing_query_repo: EventTicketingQueryRepo,
    ):
        self.event_ticketing_command_repo = event_ticketing_command_repo
        self.event_ticketing_query_repo = event_ticketing_query_repo

    @Logger.io
    async def reserve_tickets(
        self, *, event_id: int, ticket_count: int, buyer_id: int, section: str, subsection: int
    ) -> Dict[str, Any]:
        """
        預訂票務 - 使用聚合根業務邏輯

        Args:
            event_id: 活動 ID
            ticket_count: 票務數量
            buyer_id: 購買者 ID
            section: 區域
            subsection: 子區域

        Returns:
            預訂結果
        """
        Logger.base.info(
            f'🎫 [RESERVE] Starting ticket reservation for event {event_id}: '
            f'buyer_id={buyer_id}, section={section}, subsection={subsection}, count={ticket_count}'
        )

        # 驗證輸入
        if ticket_count <= 0:
            Logger.base.error(f'❌ [RESERVE] Invalid ticket count: {ticket_count}')
            raise DomainError('Ticket count must be positive', 400)
        if ticket_count > 4:
            Logger.base.error(f'❌ [RESERVE] Ticket count too high: {ticket_count} (max 4)')
            raise DomainError('Maximum 4 tickets per booking', 400)

        # 獲取 EventTicketingAggregate（只包含可用票務）
        Logger.base.info(f'🔍 [RESERVE] Loading event aggregate for event {event_id}')
        event_aggregate = await self.event_ticketing_query_repo.get_event_aggregate_by_id_with_available_tickets_only(
            event_id=event_id
        )

        if not event_aggregate:
            Logger.base.error(f'❌ [RESERVE] Event {event_id} not found')
            raise NotFoundError('Event not found')

        Logger.base.info(
            f'📊 [RESERVE] Event {event_id} loaded: {event_aggregate.available_tickets_count} available tickets'
        )

        # 根據區域篩選可用票務
        if section and subsection:
            Logger.base.info(f'🎯 [RESERVE] Filtering tickets by section {section}-{subsection}')
            available_tickets = event_aggregate.get_tickets_by_section(
                section=section, subsection=subsection
            )
            # 只取可用的票務
            available_tickets = [t for t in available_tickets if t.status.value == 'available']
            Logger.base.info(
                f'📍 [RESERVE] Found {len(available_tickets)} available tickets in section {section}-{subsection}'
            )
        else:
            Logger.base.info('🌐 [RESERVE] Using all available tickets (no section filter)')
            available_tickets = event_aggregate.get_available_tickets()
            Logger.base.info(f'🎫 [RESERVE] Total available tickets: {len(available_tickets)}')

        if len(available_tickets) < ticket_count:
            Logger.base.error(
                f'❌ [RESERVE] Not enough available tickets: {len(available_tickets)} < {ticket_count}'
            )
            raise DomainError('Not enough available tickets', 400)

        # 選擇要預訂的票務（前 n 張可用票務）
        tickets_to_reserve = available_tickets[:ticket_count]
        ticket_ids_to_reserve = [t.id for t in tickets_to_reserve if t.id is not None]

        Logger.base.info(
            f'🎯 [RESERVE] Selected tickets for reservation: {[t.seat_identifier for t in tickets_to_reserve]}'
        )

        # 通過聚合根執行預訂業務邏輯
        Logger.base.info('🔒 [RESERVE] Executing reservation through aggregate root')
        reserved_tickets = event_aggregate.reserve_tickets(
            ticket_ids=ticket_ids_to_reserve, buyer_id=buyer_id
        )

        # 更新聚合根
        Logger.base.info('💾 [RESERVE] Updating event aggregate in database')
        await self.event_ticketing_command_repo.update_event_aggregate(
            event_aggregate=event_aggregate
        )

        # Transaction is handled by the repository layer
        Logger.base.info('✅ [RESERVE] Event aggregate updated successfully')

        # 詳細的成功日誌
        self._log_reservation_details(event_id, buyer_id, reserved_tickets, event_aggregate)

        return {
            'success': True,
            'event_id': event_id,
            'buyer_id': buyer_id,
            'reserved_tickets': [
                {
                    'id': ticket.id,
                    'seat_identifier': ticket.seat_identifier,
                    'section': ticket.section,
                    'subsection': ticket.subsection,
                    'row': ticket.row,
                    'seat': ticket.seat,
                    'price': ticket.price,
                }
                for ticket in reserved_tickets
            ],
            'total_price': sum(ticket.price for ticket in reserved_tickets),
            'reservation_summary': {
                'total_tickets_reserved': len(reserved_tickets),
                'total_amount': sum(ticket.price for ticket in reserved_tickets),
                'event_remaining_tickets': event_aggregate.available_tickets_count,
            },
        }

    @Logger.io
    async def reserve_specific_tickets(
        self, *, event_id: int, ticket_ids: List[int], buyer_id: int
    ) -> Dict[str, Any]:
        """
        預訂特定票務

        Args:
            event_id: 活動 ID
            ticket_ids: 要預訂的票務 ID 列表
            buyer_id: 購買者 ID

        Returns:
            預訂結果
        """
        Logger.base.info(
            f'🎯 [RESERVE_SPECIFIC] Starting specific ticket reservation for event {event_id}: '
            f'buyer_id={buyer_id}, ticket_ids={ticket_ids}'
        )

        if not ticket_ids:
            Logger.base.error('❌ [RESERVE_SPECIFIC] Empty ticket ID list')
            raise DomainError('Ticket IDs cannot be empty', 400)
        if len(ticket_ids) > 4:
            Logger.base.error(f'❌ [RESERVE_SPECIFIC] Too many tickets: {len(ticket_ids)} (max 4)')
            raise DomainError('Maximum 4 tickets per booking', 400)

        # 獲取完整的 EventTicketingAggregate
        Logger.base.info(
            f'🔍 [RESERVE_SPECIFIC] Loading complete event aggregate for event {event_id}'
        )
        event_aggregate = await self.event_ticketing_query_repo.get_event_aggregate_by_id(
            event_id=event_id
        )

        if not event_aggregate:
            Logger.base.error(f'❌ [RESERVE_SPECIFIC] Event {event_id} not found')
            raise NotFoundError('Event not found')

        Logger.base.info(
            f'📊 [RESERVE_SPECIFIC] Event {event_id} loaded: '
            f'{event_aggregate.total_tickets_count} total tickets, '
            f'{event_aggregate.available_tickets_count} available'
        )

        # 驗證所有票務都存在且可用
        ticket_details = []
        for ticket_id in ticket_ids:
            ticket = event_aggregate._find_ticket_by_id(ticket_id)
            if not ticket:
                Logger.base.error(
                    f'❌ [RESERVE_SPECIFIC] Ticket {ticket_id} not found in event {event_id}'
                )
                raise NotFoundError(f'Ticket {ticket_id} not found')
            if ticket.status.value != 'available':
                Logger.base.error(
                    f'❌ [RESERVE_SPECIFIC] Ticket {ticket_id} not available: status={ticket.status.value}'
                )
                raise DomainError(f'Ticket {ticket_id} is not available', 400)

            ticket_details.append(f'{ticket.seat_identifier}(${ticket.price})')

        Logger.base.info(f'✅ [RESERVE_SPECIFIC] All tickets validated: {ticket_details}')

        # 通過聚合根執行預訂
        Logger.base.info('🔒 [RESERVE_SPECIFIC] Executing reservation through aggregate root')
        reserved_tickets = event_aggregate.reserve_tickets(ticket_ids=ticket_ids, buyer_id=buyer_id)

        # 更新聚合根
        Logger.base.info('💾 [RESERVE_SPECIFIC] Updating event aggregate in database')
        await self.event_ticketing_command_repo.update_event_aggregate(
            event_aggregate=event_aggregate
        )

        # Transaction is handled by the repository layer
        Logger.base.info('✅ [RESERVE_SPECIFIC] Event aggregate updated successfully')

        # 詳細的成功日誌
        self._log_reservation_details(event_id, buyer_id, reserved_tickets, event_aggregate)

        return {
            'success': True,
            'event_id': event_id,
            'buyer_id': buyer_id,
            'reserved_tickets': [
                {
                    'id': ticket.id,
                    'seat_identifier': ticket.seat_identifier,
                    'section': ticket.section,
                    'subsection': ticket.subsection,
                    'row': ticket.row,
                    'seat': ticket.seat,
                    'price': ticket.price,
                }
                for ticket in reserved_tickets
            ],
            'total_price': sum(ticket.price for ticket in reserved_tickets),
            'reservation_summary': {
                'total_tickets_reserved': len(reserved_tickets),
                'total_amount': sum(ticket.price for ticket in reserved_tickets),
                'event_remaining_tickets': event_aggregate.available_tickets_count,
            },
        }

    def _log_reservation_details(
        self,
        event_id: int,
        buyer_id: int,
        reserved_tickets: List,
        event_aggregate: EventTicketingAggregate,
    ) -> None:
        """記錄詳細的預訂信息"""
        try:
            # 按區域分組統計
            section_stats = {}
            total_amount = 0

            for ticket in reserved_tickets:
                section_key = f'{ticket.section}-{ticket.subsection}'
                if section_key not in section_stats:
                    section_stats[section_key] = {'count': 0, 'amount': 0, 'seats': []}

                section_stats[section_key]['count'] += 1
                section_stats[section_key]['amount'] += ticket.price
                section_stats[section_key]['seats'].append(f'R{ticket.row}S{ticket.seat}')
                total_amount += ticket.price

            # 記錄每個區域的詳細信息
            for section_key, stats in section_stats.items():
                Logger.base.info(
                    f'🎫 [RESERVE_DETAIL] Section {section_key}: '
                    f'{stats["count"]} tickets, ${stats["amount"]}, '
                    f'seats: {", ".join(stats["seats"])}'
                )

            # 記錄總體統計
            Logger.base.info(
                f'💰 [RESERVE_SUMMARY] Event {event_id} | Buyer {buyer_id} | '
                f'Reserved: {len(reserved_tickets)} tickets | '
                f'Total: ${total_amount} | '
                f'Remaining: {event_aggregate.available_tickets_count}/{event_aggregate.total_tickets_count}'
            )

            # 記錄活動狀態變化
            if event_aggregate.available_tickets_count == 0:
                Logger.base.info(f'🔥 [RESERVE_STATUS] Event {event_id} is now SOLD OUT!')
            elif event_aggregate.available_tickets_count <= 10:
                Logger.base.warning(
                    f'⚠️ [RESERVE_STATUS] Event {event_id} is running low: '
                    f'only {event_aggregate.available_tickets_count} tickets remaining'
                )

        except Exception as e:
            Logger.base.error(f'❌ [RESERVE_LOG] Failed to log reservation details: {e}')
            # 不拋出異常，因為預訂已經成功
