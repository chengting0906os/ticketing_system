"""Mock Email Service for demonstration."""

from datetime import datetime
from typing import List, Optional

from src.shared.logging.loguru_io import Logger


class MockEmailService:
    """Mock email service that prints to console instead of sending real emails."""

    def __init__(self, debug: bool = True):
        self.debug = debug
        self.sent_emails: List[dict] = []  # Store sent emails for testing

    @Logger.io
    async def send_email(
        self, to: str, subject: str, body: str, cc: Optional[List[str]] = None
    ) -> bool:
        email_data = {
            'to': to,
            'subject': subject,
            'body': body,
            'cc': cc or [],
            'sent_at': datetime.now(),
        }

        self.sent_emails.append(email_data)

        if self.debug:
            print('\n' + '=' * 50)
            print('📧 MOCK EMAIL SENT')
            print('=' * 50)
            print(f'To: {to}')
            if cc:
                print(f'CC: {", ".join(cc)}')
            print(f'Subject: {subject}')
            print(f'Time: {email_data["sent_at"].strftime("%Y-%m-%d %H:%M:%S")}')
            print('-' * 50)
            print('Body:')
            print(body)
            print('=' * 50 + '\n')

        return True

    @Logger.io
    async def send_order_confirmation(
        self, buyer_email: str, order_id: int, product_name: str, price: int
    ):
        """Send order confirmation email."""
        subject = f'Order Confirmation - Order #{order_id}'
        body = f"""
        Dear Customer,

        Thank you for your order!

        Order Details:
        --------------
        Order ID: #{order_id}
        Product: {product_name}
        Price: ${price / 100:.2f}
        Status: Pending Payment

        Please complete your payment to process this order.

        Best regards,
        Shopping Platform Team
        """
        await self.send_email(buyer_email, subject, body.strip())

    @Logger.io
    async def send_payment_confirmation(
        self, buyer_email: str, order_id: int, product_name: str, paid_amount: int
    ):
        """Send payment confirmation email."""
        subject = f'Payment Confirmed - Order #{order_id}'
        body = f"""
        Dear Customer,

        Your payment has been successfully processed!

        Payment Details:
        ----------------
        Order ID: #{order_id}
        Product: {product_name}
        Amount Paid: ${paid_amount / 100:.2f}
        Status: Paid

        Your order is now being processed.

        Best regards,
        Shopping Platform Team
        """
        await self.send_email(buyer_email, subject, body.strip())

    @Logger.io
    async def send_order_cancellation(
        self, buyer_email: str, order_id: int, product_name: str, reason: Optional[str] = None
    ):
        """Send order cancellation email."""
        subject = f'Order Cancelled - Order #{order_id}'
        body = f"""
        Dear Customer,

        Your order has been cancelled.

        Cancellation Details:
        --------------------
        Order ID: #{order_id}
        Product: {product_name}
        {f'Reason: {reason}' if reason else ''}

        If you have any questions, please contact our support team.

        Best regards,
        Shopping Platform Team
        """
        await self.send_email(buyer_email, subject, body.strip())

    @Logger.io
    async def notify_seller_new_order(
        self, seller_email: str, order_id: int, product_name: str, buyer_name: str, price: int
    ):
        """Notify seller about new order."""
        subject = f'New Order Received - Order #{order_id}'
        body = f"""
        Dear Seller,

        You have received a new order!

        Order Details:
        --------------
        Order ID: #{order_id}
        Product: {product_name}
        Buyer: {buyer_name}
        Price: ${price / 100:.2f}

        The buyer will complete payment soon.

        Best regards,
        Shopping Platform Team
        """
        await self.send_email(seller_email, subject, body.strip())


# Global instance for dependency injection
mock_email_service = MockEmailService(debug=True)


@Logger.io
def get_mock_email_service() -> MockEmailService:
    return mock_email_service
