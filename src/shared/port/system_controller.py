from datetime import datetime, timedelta

from fastapi import APIRouter, status
from sqlalchemy import text

from src.shared.config.db_setting import async_session_maker
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import SqlAlchemyUnitOfWork


router = APIRouter(prefix='/system', tags=['system-maintenance'])


@router.post('/cleanup-expired-reservations', status_code=status.HTTP_200_OK)
@Logger.io
async def cleanup_expired_reservations():
    """System endpoint to cleanup expired reservations."""
    # Find tickets reserved more than 15 minutes ago
    cutoff_time = datetime.now() - timedelta(minutes=15)

    # Get all expired reserved tickets
    ticket_ids = []
    async with async_session_maker() as session:
        uow = SqlAlchemyUnitOfWork(session)
        async with uow:
            # This is a simplified implementation - in production you'd have a proper use case
            result = await uow.session.execute(
                text("""
                SELECT id FROM ticket
                WHERE status = 'reserved'
                AND reserved_at < :cutoff_time
                """),
                {'cutoff_time': cutoff_time},
            )
            ticket_ids = [row[0] for row in result.fetchall()]

            if ticket_ids:
                # Update expired tickets back to available
                await uow.session.execute(
                    text("""
                    UPDATE ticket
                    SET status = 'available', buyer_id = NULL, reserved_at = NULL
                    WHERE id = ANY(:ticket_ids)
                    """),
                    {'ticket_ids': ticket_ids},
                )
            await uow.commit()

    return {
        'message': f'Cleaned up {len(ticket_ids)} expired reservations',
        'count': len(ticket_ids),
    }
