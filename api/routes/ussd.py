from datetime import datetime
from fastapi import APIRouter, Request, Form, HTTPException, Depends
from typing import Dict, Any
from sqlalchemy import func
from sqlalchemy.orm import Session
from models.payment import Payment as PaymentModel, PaymentStatus as PaymentStatusModel
from models.tenant import Issue as IssueModel
from services.n8n_service import n8n_service
import logging
from services.ussd_service import USSDService
from core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/ussd",
)

@router.post("/callback")
async def ussd_callback(
        request: Request,
        sessionId: str = Form(...),
        serviceCode: str = Form(...),
        phoneNumber: str = Form(...),
        text: str = Form(""),
        db: Session = Depends(get_db),
) -> Dict[str, str]:
    """
    Handle USSD callback from Africa's Talking
    """
    logger.info(f"USSD callback - Session: {sessionId}, Phone: {phoneNumber}, Text: {text}")

    try:
        # Create a per-request USSDService with the DB session
        ussd_service = USSDService(db)

        # Parse USSD input and get response
        response_data = await ussd_service.parse_ussd_input(
            text=text,
            session_id=sessionId,
            phone_number=phoneNumber,
            service_code=serviceCode
        )

        # Return response in Africa's Talking format
        return {
            "response": response_data["response"],
            "session_id": response_data["session_id"],
            "should_close": str(response_data["should_close"]).lower()
        }

    except Exception as e:
        logger.error(f"USSD callback error: {str(e)}")
        return {
            "response": "END An error occurred. Please try again.",
            "session_id": sessionId,
            "should_close": "true"
        }


@router.post("/tenants/{tenant_id}/balance")
async def check_balance(tenant_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Check tenant balance via USSD (simulated)
    """
    total_due = db.query(func.sum(PaymentModel.amount)).filter(
        PaymentModel.tenant_id == tenant_id,
        PaymentModel.status.in_([PaymentStatusModel.PENDING, PaymentStatusModel.OVERDUE])
    ).scalar() or 0

    total_paid = db.query(func.sum(PaymentModel.amount_paid)).filter(
        PaymentModel.tenant_id == tenant_id,
        PaymentModel.status == PaymentStatusModel.COMPLETED
    ).scalar() or 0

    return total_due - total_paid


@router.post("/issue/report")
async def report_issue(
        phone: str,
        category: str,
        description: str,
        db: Session = Depends(get_db),
        tenant_id: int = None
) -> Dict[str, Any]:
    """
    Report issue via USSD
    tenant_id may be provided from the USSD session handling layer; if not provided, it must be supplied.
    """
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    issue = IssueModel(
        tenant_id=tenant_id,
        category=category,
        description=description,
        status="open"
    )

    db.add(issue)
    db.commit()
    db.refresh(issue)
    # Trigger n8n workflow
    await n8n_service.trigger_workflow('issue_reported', {
        'phone': phone,
        'category': category,
        'description': description
    })

    return {
        "success": True,
        "message": "Issue reported successfully",
        "ticket_id": "ISS" + str(int(datetime.now().timestamp()))
    }