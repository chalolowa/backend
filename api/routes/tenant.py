from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime
from core.database import get_db
from models.payment import Payment as PaymentModel, PaymentStatus as PaymentStatusModel
from schemas.tenant import TenantCreate, TenantUpdate, Issue as IssueSchema, IssueCreate, Tenant
from api.deps import get_current_landlord
from services.sms_service import sms_service
from services.n8n_service import n8n_service
from services.accounting_service import accounting_service
from models.property import Property as PropertyModel
from models.property import Unit as UnitModel
from models.tenant import Tenant as TenantModel, Issue as IssueModel
from models.reminder import Reminder, ReminderType, ReminderStatus
from datetime import datetime

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("", response_model=Tenant)
async def create_tenant(
        tenant_data: TenantCreate,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Create a new tenant
    """
    # Verify property belongs to landlord
    property = db.query(PropertyModel).filter(
        PropertyModel.id == tenant_data.property_id,
        PropertyModel.landlord_id == current_landlord.id
    ).first()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Check if unit is available
    if tenant_data.unit_id:
        unit = db.query(UnitModel).filter(UnitModel.id == tenant_data.unit_id).first()
        if unit and unit.is_occupied:
            raise HTTPException(status_code=400, detail="Unit is already occupied")

    # Create tenant
    db_tenant = TenantModel(
        landlord_id=current_landlord.id,
        **tenant_data.dict()
    )
    db.add(db_tenant)
    db.flush()

    # Update unit occupancy
    if tenant_data.unit_id:
        unit = db.query(UnitModel).filter(UnitModel.id == tenant_data.unit_id).first()
        unit.is_occupied = True
        unit.status = "occupied"
        db.add(unit)

    db.commit()
    db.refresh(db_tenant)

    # Create initial payment record
    from models.payment import Payment, PaymentStatus
    first_payment = PaymentModel(
        landlord_id=current_landlord.id,
        tenant_id=db_tenant.id,
        property_id=tenant_data.property_id,
        amount=tenant_data.monthly_rent,
        due_date=date.today().replace(day=tenant_data.rent_due_day),
        status=PaymentStatusModel.PENDING
    )
    db.add(first_payment)
    db.commit()

    # Send welcome SMS
    welcome_msg = f"Welcome {db_tenant.first_name}! You're now registered at {property.name}. Your rent of KES {db_tenant.monthly_rent:,.0f} is due on the {db_tenant.rent_due_day}th each month. Dial *117# for self-service."
    await sms_service.send_sms(db_tenant.phone, welcome_msg)

    # Trigger n8n workflow
    await n8n_service.trigger_new_tenant({
        'tenant_id': db_tenant.id,
        'name': f"{db_tenant.first_name} {db_tenant.last_name}",
        'phone': db_tenant.phone,
        'property': property.name
    })

    return db_tenant


@router.get("", response_model=List[Tenant])
async def list_tenants(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db),
        property_id: int = None,
        is_active: bool = True,
        skip: int = 0,
        limit: int = 100
):
    """
    List tenants for current landlord
    """
    query = db.query(TenantModel).filter(
        TenantModel.landlord_id == current_landlord.id,
        TenantModel.is_active == is_active
    )

    if property_id:
        query = query.filter(TenantModel.property_id == property_id)

    tenants = query.offset(skip).limit(limit).all()

    # Add balance for each tenant
    for tenant in tenants:
        tenant.balance = accounting_service.get_tenant_balance(db, tenant.id)

    return tenants


@router.get("/{tenant_id}", response_model=Tenant)
async def get_tenant(
        tenant_id: int,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Get tenant by ID
    """
    tenant = db.query(TenantModel).filter(
        TenantModel.id == tenant_id,
        TenantModel.landlord_id == current_landlord.id
    ).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Add balance and payment info
    tenant.balance = accounting_service.get_tenant_balance(db, tenant_id)

    # Get last payment
    last_payment = db.query(PaymentModel).filter(
        PaymentModel.tenant_id == tenant_id,
        PaymentModel.status == PaymentStatusModel.COMPLETED
    ).order_by(PaymentModel.payment_date.desc()).first()

    if last_payment:
        tenant.last_payment_date = last_payment.payment_date
        tenant.last_payment_amount = last_payment.amount

    # Get next payment due
    next_payment = db.query(PaymentModel).filter(
        PaymentModel.tenant_id == tenant_id,
        PaymentModel.status.in_([PaymentStatusModel.PENDING, PaymentStatusModel.OVERDUE])
    ).order_by(PaymentModel.due_date.asc()).first()

    if next_payment:
        tenant.next_payment_date = next_payment.due_date

    return tenant


@router.put("/{tenant_id}", response_model=Tenant)
async def update_tenant(
        tenant_id: int,
        tenant_update: TenantUpdate,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Update tenant
    """
    tenant = db.query(TenantModel).filter(
        TenantModel.id == tenant_id,
        TenantModel.landlord_id == current_landlord.id
    ).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    for key, value in tenant_update.dict(exclude_unset=True).items():
        setattr(tenant, key, value)

    db.commit()
    db.refresh(tenant)
    return tenant


@router.post("/{tenant_id}/remind")
async def send_reminder(
        tenant_id: int,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Send payment reminder to tenant
    """
    tenant = db.query(TenantModel).filter(
        TenantModel.id == tenant_id,
        TenantModel.landlord_id == current_landlord.id
    ).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Get current balance
    balance = accounting_service.get_tenant_balance(db, tenant_id)

    # Send SMS
    result = await sms_service.send_payment_reminder(
        tenant_name=tenant.first_name,
        phone=tenant.phone,
        amount=balance,
        due_date=date.today().strftime("%Y-%m-%d")
    )

    if result["success"]:
        # Create reminder record
        reminder = Reminder(
            landlord_id=current_landlord.id,
            tenant_id=tenant_id,
            reminder_type=ReminderType.PAYMENT,
            message=f"Payment reminder for KES {balance:,.0f}",
            delivery_method="sms",
            status=ReminderStatus.SENT,
            sent_at=datetime.utcnow(),
            at_message_id=result.get("message_id")
        )
        db.add(reminder)
        db.commit()

    return result


@router.get("/{tenant_id}/balance")
async def get_tenant_balance(
        tenant_id: int,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Get tenant's current balance
    """
    balance = accounting_service.get_tenant_balance(db, tenant_id)
    return {"tenant_id": tenant_id, "balance": balance}


# Issue endpoints
@router.post("/issues", response_model=IssueSchema)
async def create_issue(
        issue_data: IssueCreate,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Create a new issue (from tenant or landlord)
    """
    # Verify tenant belongs to landlord
    tenant = db.query(TenantModel).filter(
        TenantModel.id == issue_data.tenant_id,
        TenantModel.landlord_id == current_landlord.id
    ).first()

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

    # Trigger n8n workflow
    await n8n_service.trigger_issue_reported({
        'issue_id': db_issue.id,
        'tenant': f"{tenant.first_name} {tenant.last_name}",
        'category': db_issue.category,
        'description': db_issue.description
    })

    return db_issue


@router.get("/issues", response_model=List[IssueSchema])
async def list_issues(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db),
        status: str = None,
        skip: int = 0,
        limit: int = 100
):
    """
    List all issues
    """
    query = db.query(IssueModel).join(TenantModel).filter(
        TenantModel.landlord_id == current_landlord.id
    )

    if status:
        query = query.filter(IssueModel.status == status)

    issues = query.order_by(IssueModel.created_at.desc()).offset(skip).limit(limit).all()
    return issues