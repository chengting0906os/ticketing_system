"""
Booking and Reserving Command Repository - ScyllaDB Implementation

使用 ScyllaDB 實現座位預訂
配合 Kvrocks 分散式鎖保證一致性
"""

import time
from typing import Dict, List, Optional
from uuid import UUID

from opentelemetry import trace

from src.platform.database.scylla_setting import get_scylla_session
from src.platform.logging.loguru_io import Logger
from src.platform.state.distributed_lock import DistributedLock
from src.service.ticketing.app.interface import IBookingAndReservingCommandRepo


class BookingAndReservingCommandRepoScyllaImpl(IBookingAndReservingCommandRepo):
    """
    座位預訂命令倉儲 - ScyllaDB 實作

    策略：
    1. Kvrocks 分散式鎖（subsection 級別）
    2. ScyllaDB 原子性更新座位狀態
    3. 無需 Kvrocks bitmap，簡化狀態管理
    """

    def __init__(self):
        self.lock = DistributedLock()
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def reserve_seats_atomic(
        self,
        *,
        event_id: UUID,
        booking_id: UUID,
        buyer_id: UUID,
        mode: str,
        seat_ids: Optional[List[str]] = None,
        section: Optional[str] = None,
        subsection: Optional[int] = None,
        quantity: Optional[int] = None,
    ) -> Dict:
        """
        原子性預訂座位 - 路由到對應的預訂模式

        策略：
        - best_available: 系統自動選擇最佳連續座位
        - manual: 用戶手動指定座位
        """
        Logger.base.info(f'🎯 [SCYLLA] Routing reservation (mode={mode}) for booking {booking_id}')

        if mode == 'best_available':
            # Validate required parameters for best_available mode
            if not section or subsection is None or not quantity:
                return {
                    'success': False,
                    'reserved_seats': [],
                    'error_message': 'Best available mode requires section, subsection, and quantity',
                }
            return await self.find_and_reserve_tickets_by_best_available_mode(
                event_id=event_id,
                section=section,
                subsection=subsection,
                quantity=quantity,
                booking_id=booking_id,
                buyer_id=buyer_id,
            )
        else:
            # Manual mode
            return await self.find_and_reserve_tickets_by_manual_mode(
                event_id=event_id,
                booking_id=booking_id,
                buyer_id=buyer_id,
                seat_ids=seat_ids,
                section=section,
                subsection=subsection,
            )

    @Logger.io
    async def find_and_reserve_tickets_by_manual_mode(
        self,
        *,
        event_id: UUID,
        booking_id: UUID,
        buyer_id: UUID,
        seat_ids: Optional[List[str]] = None,
        section: Optional[str] = None,
        subsection: Optional[int] = None,
    ) -> Dict:
        """
        手動模式預訂座位 - 用戶指定具體座位

        流程：
        1. 獲取 subsection 級別的分散式鎖
        2. 逐個檢查並預訂指定座位
        3. 釋放鎖
        """
        start_time = time.perf_counter()
        Logger.base.info(
            f'🎯 [SCYLLA] Manual reservation for booking {booking_id}, seats={len(seat_ids) if seat_ids else 0}'
        )

        # Validate required parameters
        if not seat_ids or not section or subsection is None:
            return {
                'success': False,
                'reserved_seats': [],
                'error_message': 'Manual mode requires seat_ids, section, and subsection',
            }

        # Type narrowing: at this point seat_ids is guaranteed to be List[str]
        validated_seat_ids: List[str] = seat_ids

        # Step 1: Acquire distributed lock at subsection level (Kvrocks)
        lock_key = f'lock:event:{event_id}:subsection:{section}-{subsection}'
        lock_start = time.perf_counter()

        with self.tracer.start_as_current_span(
            'lock.acquire',
            attributes={
                'lock.key': lock_key,
                'lock.subsection': f'{section}-{subsection}',
            },
        ):
            lock_acquired = await self.lock.acquire_lock(key=lock_key, ttl=10)

        lock_time = (time.perf_counter() - lock_start) * 1000

        if not lock_acquired:
            Logger.base.warning(f'⏳ [SCYLLA] Failed to acquire lock for {section}-{subsection}')
            return {
                'success': False,
                'reserved_seats': [],
                'error_message': 'Failed to acquire lock, please retry',
            }

        Logger.base.info(f'⏱️ [SCYLLA] Lock acquired in {lock_time:.2f}ms')

        try:
            # Step 2: Reserve seats using ScyllaDB
            db_start = time.perf_counter()

            span = self.tracer.start_span(
                'db.reserve_seats_by_scylla',
                attributes={
                    'db.system': 'scylladb',
                    'db.operation': 'update',
                    'seat.count': len(validated_seat_ids),
                    'event.id': str(event_id),
                    'booking.id': str(booking_id),
                },
            )
            with trace.use_span(span, end_on_exit=True):
                span.add_event('Starting seat reservation in ScyllaDB')

                session = await get_scylla_session()

                reserved_seats = []
                failed_seats = []
                check_time_total: float = 0.0
                update_time_total: float = 0.0

                for seat_id in validated_seat_ids:
                    # Parse seat_id (format: "row-seat" or "section-subsection-row-seat")
                    parts = seat_id.split('-')
                    row: str
                    seat_num: str
                    if len(parts) == 2:
                        row, seat_num = parts
                    elif len(parts) == 4:
                        _, _, row, seat_num = parts
                    else:
                        Logger.base.warning(f'⚠️ [SCYLLA] Invalid seat_id format: {seat_id}')
                        failed_seats.append(seat_id)
                        continue

                    # Check if seat is available first
                    check_start = time.perf_counter()
                    with self.tracer.start_as_current_span(
                        'db.check_seat',
                        attributes={
                            'db.statement': 'SELECT status FROM ticket WHERE...',
                            'seat.id': seat_id,
                        },
                    ):
                        check_query = """
                            SELECT status FROM ticket
                            WHERE event_id = %s
                              AND section = %s
                              AND subsection = %s
                              AND row_number = %s
                              AND seat_number = %s
                        """
                        result = session.execute(
                            check_query, (event_id, section, subsection, int(row), int(seat_num))
                        )
                        row_data = result.one()
                    check_time_total += (time.perf_counter() - check_start) * 1000

                    if not row_data or row_data.status != 'available':
                        Logger.base.warning(
                            f'⚠️ [SCYLLA] Seat {seat_id} is not available (status={row_data.status if row_data else "not_found"})'
                        )
                        failed_seats.append(seat_id)
                        continue

                    # Regular UPDATE (Kafka ordering + lock guarantee safety)
                    update_start = time.perf_counter()
                    with self.tracer.start_as_current_span(
                        'db.update_seat',
                        attributes={
                            'db.statement': 'UPDATE ticket SET status=reserved WHERE...',
                            'seat.id': seat_id,
                        },
                    ):
                        update_query = """
                            UPDATE ticket
                            SET status = 'reserved',
                                buyer_id = %s,
                                updated_at = toTimestamp(now()),
                                reserved_at = toTimestamp(now())
                            WHERE event_id = %s
                              AND section = %s
                              AND subsection = %s
                              AND row_number = %s
                              AND seat_number = %s
                        """

                        session.execute(
                            update_query,
                            (buyer_id, event_id, section, subsection, int(row), int(seat_num)),
                        )
                    update_time_total += (time.perf_counter() - update_start) * 1000

                    full_seat_id = f'{section}-{subsection}-{row}-{seat_num}'
                    reserved_seats.append(full_seat_id)
                    Logger.base.info(f'✅ [SCYLLA] Reserved seat: {full_seat_id}')

                # Step 3: Get ticket price (assume all seats in same subsection have same price)
                price_start = time.perf_counter()
                if reserved_seats:
                    with self.tracer.start_as_current_span(
                        'db.get_price',
                        attributes={
                            'db.statement': 'SELECT price FROM ticket WHERE...',
                        },
                    ):
                        first_seat_parts = reserved_seats[0].split('-')
                        _, _, row, seat_num = first_seat_parts
                        price_query = """
                            SELECT price FROM ticket
                            WHERE event_id = %s
                              AND section = %s
                              AND subsection = %s
                              AND row_number = %s
                              AND seat_number = %s
                        """
                        price_result = session.execute(
                            price_query, (event_id, section, subsection, int(row), int(seat_num))
                        )
                        price_row = price_result.one()
                        ticket_price = price_row.price if price_row else 0
                else:
                    ticket_price = 0
                price_time = (time.perf_counter() - price_start) * 1000
                db_total_time = (time.perf_counter() - db_start) * 1000

                Logger.base.info(
                    f'⏱️ [SCYLLA] DB operations: '
                    f'check={check_time_total:.2f}ms, '
                    f'update={update_time_total:.2f}ms, '
                    f'price={price_time:.2f}ms, '
                    f'total_db={db_total_time:.2f}ms'
                )

                # Mark completion in span
                span.add_event(
                    'Completed seat reservation',
                    attributes={
                        'reserved.count': len(reserved_seats),
                        'failed.count': len(failed_seats),
                        'total.time_ms': db_total_time,
                    },
                )

                if failed_seats:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, 'Some seats unavailable'))
                else:
                    span.set_status(trace.Status(trace.StatusCode.OK))

            if failed_seats:
                Logger.base.warning(f'⚠️ [SCYLLA] Some seats unavailable: {failed_seats}')
                return {
                    'success': False,
                    'reserved_seats': reserved_seats,
                    'error_message': f'Some seats are not available: {failed_seats}',
                }

            total_time = (time.perf_counter() - start_time) * 1000
            Logger.base.info(
                f'✅ [SCYLLA] Reserved {len(reserved_seats)} seats, price={ticket_price}, '
                f'total_time={total_time:.2f}ms'
            )
            return {
                'success': True,
                'reserved_seats': reserved_seats,
                'ticket_price': ticket_price,
                'error_message': None,
            }

        except Exception as e:
            total_time = (time.perf_counter() - start_time) * 1000
            Logger.base.error(f'❌ [SCYLLA] Error reserving seats: {e}, time={total_time:.2f}ms')
            return {
                'success': False,
                'reserved_seats': [],
                'error_message': f'Database error: {str(e)}',
            }
        finally:
            # Step 4: Always release lock (Kvrocks)
            release_start = time.perf_counter()
            with self.tracer.start_as_current_span(
                'lock.release',
                attributes={
                    'lock.key': lock_key,
                },
            ):
                await self.lock.release_lock(key=lock_key)
            release_time = (time.perf_counter() - release_start) * 1000
            Logger.base.info(f'⏱️ [SCYLLA] Lock released in {release_time:.2f}ms')

    @Logger.io
    async def find_and_reserve_tickets_by_best_available_mode(
        self,
        *,
        event_id: UUID,
        section: str,
        subsection: int,
        quantity: int,
        booking_id: UUID,
        buyer_id: UUID,
    ) -> Dict:
        """
        自動模式預訂座位 - 系統選擇最佳連續座位

        流程：
        1. 獲取 subsection 級別的分散式鎖
        2. 查詢可用座位並選擇最佳連續座位
        3. 批量預訂座位
        4. 釋放鎖
        """
        start_time = time.perf_counter()
        Logger.base.info(
            f'🎯 [SCYLLA] Best-available reservation: booking={booking_id}, '
            f'section={section}, subsection={subsection}, qty={quantity}'
        )

        # Step 1: Acquire distributed lock at subsection level (Kvrocks)
        lock_key = f'lock:event:{event_id}:subsection:{section}-{subsection}'
        lock_start = time.perf_counter()

        with self.tracer.start_as_current_span(
            'lock.acquire',
            attributes={
                'lock.key': lock_key,
                'lock.subsection': f'{section}-{subsection}',
            },
        ):
            lock_acquired = await self.lock.acquire_lock(key=lock_key, ttl=10)

        lock_time = (time.perf_counter() - lock_start) * 1000

        if not lock_acquired:
            Logger.base.warning(f'⏳ [SCYLLA] Failed to acquire lock for {section}-{subsection}')
            return {
                'success': False,
                'reserved_seats': [],
                'error_message': 'Failed to acquire lock, please retry',
            }

        Logger.base.info(f'⏱️ [SCYLLA] Lock acquired in {lock_time:.2f}ms')

        try:
            # Step 2: Query available seats from ScyllaDB
            query_start = time.perf_counter()

            span = self.tracer.start_span(
                'db.query_available_seats',
                attributes={
                    'db.system': 'scylladb',
                    'db.operation': 'select',
                    'db.table': 'ticket',
                    'event.id': str(event_id),
                    'section': section,
                    'subsection': subsection,
                    'seat.mode': 'best_available',
                    'seat.quantity_requested': quantity,
                },
            )
            with trace.use_span(span, end_on_exit=True):
                span.add_event('Starting query for available seats')

                session = await get_scylla_session()

                # Query available seats
                query = """
                    SELECT row_number, seat_number, price
                    FROM ticket
                    WHERE event_id = %s
                      AND section = %s
                      AND subsection = %s
                      AND status = 'available'
                    ALLOW FILTERING
                """

                result = session.execute(query, (event_id, section, subsection))
                available_seats = list(result)

                span.add_event('Query completed', attributes={'seats.found': len(available_seats)})

            query_time = (time.perf_counter() - query_start) * 1000
            Logger.base.info(
                f'⏱️ [SCYLLA] Query found {len(available_seats)} available seats in {query_time:.2f}ms'
            )

            if len(available_seats) < quantity:
                Logger.base.warning(
                    f'⚠️ [SCYLLA] Not enough seats: requested={quantity}, available={len(available_seats)}'
                )
                return {
                    'success': False,
                    'reserved_seats': [],
                    'error_message': f'Not enough seats available (requested={quantity}, available={len(available_seats)})',
                }

            # Step 3: Find best consecutive seats
            selection_start = time.perf_counter()

            # Group seats by row for consecutive seat finding
            seats_by_row = {}
            for seat in available_seats:
                row = seat.row_number
                if row not in seats_by_row:
                    seats_by_row[row] = []
                seats_by_row[row].append(seat)

            # Sort seats within each row
            for row in seats_by_row:
                seats_by_row[row].sort(key=lambda s: s.seat_number)

            # Find consecutive seats
            selected_seats = []
            for _row, seats in seats_by_row.items():
                consecutive = []
                for i, seat in enumerate(seats):
                    if i == 0 or seat.seat_number == seats[i - 1].seat_number + 1:
                        consecutive.append(seat)
                    else:
                        if len(consecutive) >= quantity:
                            break
                        consecutive = [seat]

                    if len(consecutive) >= quantity:
                        selected_seats = consecutive[:quantity]
                        break

                if selected_seats:
                    break

            # Fallback: if no consecutive seats, just take first N available
            if not selected_seats:
                Logger.base.info(
                    f'ℹ️ [SCYLLA] No consecutive seats, using first {quantity} available'
                )
                selected_seats = available_seats[:quantity]

            selection_time = (time.perf_counter() - selection_start) * 1000
            Logger.base.info(f'⏱️ [SCYLLA] Seat selection took {selection_time:.2f}ms')

            # Step 4: Reserve selected seats
            reservation_start = time.perf_counter()

            span = self.tracer.start_span(
                'db.reserve_selected_seats',
                attributes={
                    'db.system': 'scylladb',
                    'db.operation': 'update',
                    'seat.count': len(selected_seats),
                    'event.id': str(event_id),
                    'booking.id': str(booking_id),
                },
            )
            with trace.use_span(span, end_on_exit=True):
                span.add_event('Starting batch seat reservation')

                reserved_seats = []
                ticket_price = selected_seats[0].price if selected_seats else 0

                for seat in selected_seats:
                    with self.tracer.start_as_current_span(
                        'db.update_seat',
                        attributes={
                            'db.statement': 'UPDATE ticket SET status=reserved WHERE...',
                            'seat.id': f'{seat.row_number}-{seat.seat_number}',
                        },
                    ):
                        update_query = """
                            UPDATE ticket
                            SET status = 'reserved',
                                buyer_id = %s,
                                updated_at = toTimestamp(now()),
                                reserved_at = toTimestamp(now())
                            WHERE event_id = %s
                              AND section = %s
                              AND subsection = %s
                              AND row_number = %s
                              AND seat_number = %s
                        """

                        session.execute(
                            update_query,
                            (
                                buyer_id,
                                event_id,
                                section,
                                subsection,
                                seat.row_number,
                                seat.seat_number,
                            ),
                        )

                    seat_id = f'{section}-{subsection}-{seat.row_number}-{seat.seat_number}'
                    reserved_seats.append(seat_id)

                span.add_event(
                    'Batch reservation completed',
                    attributes={
                        'reserved.count': len(reserved_seats),
                    },
                )
                span.set_status(trace.Status(trace.StatusCode.OK))

            reservation_time = (time.perf_counter() - reservation_start) * 1000
            total_time = (time.perf_counter() - start_time) * 1000

            Logger.base.info(
                f'✅ [SCYLLA] Reserved {len(reserved_seats)} seats, price={ticket_price}, '
                f'reservation_time={reservation_time:.2f}ms, total_time={total_time:.2f}ms'
            )

            return {
                'success': True,
                'reserved_seats': reserved_seats,
                'ticket_price': ticket_price,
                'error_message': None,
            }

        except Exception as e:
            total_time = (time.perf_counter() - start_time) * 1000
            Logger.base.error(
                f'❌ [SCYLLA] Error in best-available mode: {e}, time={total_time:.2f}ms'
            )
            return {
                'success': False,
                'reserved_seats': [],
                'error_message': f'Database error: {str(e)}',
            }
        finally:
            # Step 5: Always release lock (Kvrocks)
            release_start = time.perf_counter()
            with self.tracer.start_as_current_span(
                'lock.release',
                attributes={
                    'lock.key': lock_key,
                },
            ):
                await self.lock.release_lock(key=lock_key)
            release_time = (time.perf_counter() - release_start) * 1000
            Logger.base.info(f'⏱️ [SCYLLA] Lock released in {release_time:.2f}ms')
