import httpx
from typing import Dict, Any, Optional
from core.config import N8N_WEBHOOK_URL, N8N_API_KEY
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class N8NService:
    def __init__(self):
        self.webhook_url = N8N_WEBHOOK_URL
        self.api_key = N8N_API_KEY
        self.client = httpx.AsyncClient(timeout=10.0)

    async def trigger_workflow(self, event: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger n8n workflow
        """
        if not self.webhook_url:
            logger.warning("n8n webhook URL not configured")
            return {"success": False, "error": "Webhook not configured"}

        try:
            payload = {
                "event": event,
                "timestamp": str(datetime.now(timezone.utc)),
                "data": data
            }

            headers = {
                "Content-Type": "application/json"
            }

            if self.api_key:
                headers["X-API-Key"] = self.api_key

            response = await self.client.post(
                self.webhook_url,
                json=payload,
                headers=headers
            )

            response.raise_for_status()

            logger.info(f"n8n workflow triggered for event {event}")
            return {
                "success": True,
                "response": response.json() if response.content else {}
            }

        except Exception as e:
            logger.error(f"Failed to trigger n8n workflow: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def trigger_payment_reminder(self, tenant: Dict, payment: Dict):
        """
        Trigger payment reminder workflow
        """
        return await self.trigger_workflow("payment_reminder", {
            "tenant": tenant,
            "payment": payment
        })

    async def trigger_overdue_payment(self, tenant: Dict, payment: Dict, days_overdue: int):
        """
        Trigger overdue payment workflow
        """
        return await self.trigger_workflow("overdue_payment", {
            "tenant": tenant,
            "payment": payment,
            "days_overdue": days_overdue
        })

    async def trigger_new_tenant(self, tenant: Dict):
        """
        Trigger new tenant workflow
        """
        return await self.trigger_workflow("new_tenant", {
            "tenant": tenant
        })

    async def trigger_issue_reported(self, issue: Dict):
        """
        Trigger issue reported workflow
        """
        return await self.trigger_workflow("issue_reported", {
            "issue": issue
        })

    async def trigger_payment_received(self, payment: Dict):
        """
        Trigger payment received workflow
        """
        return await self.trigger_workflow("payment_received", {
            "payment": payment
        })

    async def trigger_lease_expiring(self, tenant: Dict, days_remaining: int):
        """
        Trigger lease expiry workflow
        """
        return await self.trigger_workflow("lease_expiring", {
            "tenant": tenant,
            "days_remaining": days_remaining
        })


n8n_service = N8NService()