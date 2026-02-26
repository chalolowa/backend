from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta, datetime
from typing import List, Dict, Any

from core.database import get_db
from api.deps import require_api_key, get_current_landlord
from services.sms_service import sms_service
from services.accounting_service import accounting_service
from models.payment import Payment as PaymentModel, PaymentStatus
from models.tenant import Tenant as TenantModel
from models.reminder import Reminder, ReminderType, ReminderStatus
from models.tenant import Issue as IssueModel

router = APIRouter(prefix="", tags=["Integration"])

# --- SMS helper -------------------------------------------------------------


@router.get("/tenants/phone/{phone}")
async def get_tenant_by_phone(
        phone: str,
        db: Session = Depends(get_db),
        api_key: None = Depends(require_api_key)
):
    """Lookup tenant record by phone number.

    Used by n8n AI workflow to bootstrap context. Returns a simplified
    tenant object with the fields required by the workflow.
    """
    tenant = db.query(TenantModel).filter(TenantModel.phone == phone).first()
    if not tenant:
        return {"exists": False}

    return {
        "exists": True,
        "tenant_id": tenant.id,
        "first_name": tenant.first_name,
        "last_name": tenant.last_name,
        "phone": tenant.phone,
        "unit_number": tenant.unit_number,
        "monthly_rent": tenant.monthly_rent,
        "lease_start": tenant.lease_start.isoformat() if tenant.lease_start else None,
        "lease_end": tenant.lease_end.isoformat() if tenant.lease_end else None,
        "property_id": tenant.property_id
    }


# --- SMS helper -------------------------------------------------------------
@router.post("/sms/send")
async def send_sms(
        phone: str,
        message: str,
        db: Session = Depends(get_db),
        api_key: None = Depends(require_api_key)
):
    """Public endpoint for n8n workflows to send SMS via the service."""
    return await sms_service.send_sms(phone, message)


# --- Reminder logging ------------------------------------------------------
@router.post("/reminders/log")
async def log_reminder(
        tenant_id: int,
        reminder_type: str,
        status: str,
        payment_id: int | None = None,
        message: str | None = None,
        db: Session = Depends(get_db),
        api_key: None = Depends(require_api_key)
):
    """Record that an automated reminder was sent/attempted.

    Allows the n8n workflows to post a simple log entry which is
    persisted to the database. The endpoint is intentionally
    lightweight; missing optional fields are ignored.
    """
    # tenant lookup (ensure exists)
    tenant = db.query(TenantModel).filter(TenantModel.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # map reminder type to enum (case-insensitive)
    try:
        rtype = ReminderType(reminder_type.lower())
    except ValueError:
        rtype = ReminderType.GENERAL

    try:
        rstatus = ReminderStatus(status.lower())
    except ValueError:
        rstatus = ReminderStatus.PENDING

    text = message or f"{rtype.value} reminder"

    reminder = Reminder(
        landlord_id=tenant.landlord_id,
        tenant_id=tenant_id,
        payment_id=payment_id,
        reminder_type=rtype,
        message=text,
        status=rstatus,
        sent_at=datetime.utcnow()
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return {"success": True, "reminder_id": reminder.id}


# --- Payments / utility ----------------------------------------------------
@router.get("/payments/upcoming")
async def get_upcoming_payments(
        days: int = 3,
        db: Session = Depends(get_db),
        api_key: None = Depends(require_api_key)
) -> Dict[str, Any]:
    """Return all payments due within the next `days` days.

    This endpoint is used by scheduled n8n workflows; it ignores landlord
    authentication and instead simply returns matching records.
    """
    today = date.today()
    cutoff = today + timedelta(days=days)
    payments = db.query(PaymentModel).filter(
        PaymentModel.due_date >= today,
        PaymentModel.due_date <= cutoff,
        PaymentModel.status.in_([PaymentStatus.PENDING, PaymentStatus.PARTIAL])
    ).all()

    results: List[Dict[str, Any]] = []
    for p in payments:
        tenant = db.query(TenantModel).filter(TenantModel.id == p.tenant_id).first()
        prop_name = p.property.name if p.property else None
        results.append({
            "id": p.id,
            "tenant_id": p.tenant_id,
            "tenant_name": f"{tenant.first_name} {tenant.last_name}" if tenant else "Unknown",
            "phone": tenant.phone if tenant else None,
            "property_name": prop_name,
            "amount": p.amount,
            "due_date": p.due_date.isoformat()
        })

    return {"payments": results}


@router.get("/payments/tenant/{tenant_id}/balance")
async def tenant_balance_public(
        tenant_id: int,
        db: Session = Depends(get_db),
        api_key: None = Depends(require_api_key)
):
    """Alias endpoint used by external automations to fetch balance. """
    balance = accounting_service.get_tenant_balance(db, tenant_id)
    return {"tenant_id": tenant_id, "balance": balance}


# --- Issue creation endpoint (public) --------------------------------------
from schemas.tenant import IssueCreate

@router.post("/issues/create")
async def issue_create_public(
        issue_data: IssueCreate,
        db: Session = Depends(get_db),
        api_key: None = Depends(require_api_key)
):
    """Create an issue on behalf of a tenant (used by n8n AI workflow)."""
    tenant = db.query(TenantModel).filter(TenantModel.id == issue_data.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    db_issue = IssueModel(
        tenant_id=issue_data.tenant_id,
        category=issue_data.category,
        description=issue_data.description,
        status=issue_data.status or "open"
    )
    db.add(db_issue)
    db.commit()
    db.refresh(db_issue)

    # trigger workflow notification
    from services.n8n_service import n8n_service
    await n8n_service.trigger_issue_reported({
        'issue_id': db_issue.id,
        'tenant': f"{tenant.first_name} {tenant.last_name}",
        'category': db_issue.category,
        'description': db_issue.description
    })

    return db_issue
