import africastalking
from typing import Optional, List
from core.config import AFRICASTALKING_USERNAME, AFRICASTALKING_API_KEY, AFRICASTALKING_SENDER_ID
from fastapi.concurrency import run_in_threadpool
import logging

logger = logging.getLogger(__name__)


class SMSService:
    def __init__(self):
        # Initialize Africa's Talking
        if not AFRICASTALKING_USERNAME or not AFRICASTALKING_API_KEY:
            logger.warning(
                "AfricasTalking credentials are not set (AFRICASTALKING_USERNAME/API_KEY); "
                "SMS functionality will fail until they are provided."
            )
        africastalking.initialize(
            username=AFRICASTALKING_USERNAME,
            api_key=AFRICASTALKING_API_KEY
        )
        self.sms = africastalking.SMS
        self.sender_id = AFRICASTALKING_SENDER_ID

    async def send_sms(self, phone_number: str, message: str) -> dict:
        """
        Send a single SMS
        """
        try:
            # Format phone number (ensure it has country code)
            if not phone_number.startswith('+'):
                phone_number = f'+{phone_number}'

            response = await run_in_threadpool(
                self.sms.send,
                message=message,
                recipients=[phone_number],
                sender_id=self.sender_id
            )

            logger.info(f"SMS sent to {phone_number}: {response}")
            return {
                "success": True,
                "message_id": response['SMSMessageData']['Recipients'][0]['messageId'],
                "response": response
            }
        except Exception as e:
            logger.error(f"Failed to send SMS: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def send_bulk_sms(self, phone_numbers: List[str], message: str) -> dict:
        """
        Send bulk SMS to multiple recipients
        """
        try:
            # Format phone numbers
            formatted_numbers = []
            for num in phone_numbers:
                if not num.startswith('+'):
                    formatted_numbers.append(f'+{num}')
                else:
                    formatted_numbers.append(num)

            response = await run_in_threadpool(
                self.sms.send,
                message=message,
                recipients=formatted_numbers,
                sender_id=self.sender_id
            )

            logger.info(f"Bulk SMS sent to {len(phone_numbers)} recipients")
            return {
                "success": True,
                "response": response
            }
        except Exception as e:
            logger.error(f"Failed to send bulk SMS: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def send_payment_reminder(self, tenant_name: str, phone: str, amount: float, due_date: str):
        """
        Send payment reminder SMS
        """
        message = f"Dear {tenant_name}, your rent of KES {amount:,.0f} is due on {due_date}. Please make payment to avoid late fees. Dial *117# to pay via M-Pesa."
        return await self.send_sms(phone, message)

    async def send_payment_confirmation(self, tenant_name: str, phone: str, amount: float, receipt_no: str):
        """
        Send payment confirmation SMS
        """
        message = f"Thank you {tenant_name}! We've received your payment of KES {amount:,.0f}. Receipt #{receipt_no} has been sent to your email."
        return await self.send_sms(phone, message)

    async def send_overdue_reminder(self, tenant_name: str, phone: str, amount: float, days_overdue: int):
        """
        Send overdue payment reminder
        """
        message = f"URGENT: {tenant_name}, your rent payment of KES {amount:,.0f} is now {days_overdue} days overdue. Please pay immediately to avoid further action. Dial *117# to pay now."
        return await self.send_sms(phone, message)


sms_service = SMSService()