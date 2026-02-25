from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, date
from core.database import get_db
from models.payment import Payment as PaymentModel, PaymentStatus, PaymentMethod, Receipt as ReceiptModel
from models.tenant import Tenant as TenantModel
from schemas.payment import Payment, PaymentCreate, Receipt, PaymentSummary
from api.deps import get_current_landlord
from services.sms_service import sms_service
from services.n8n_service import n8n_service
from services.accounting_service import accounting_service


router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("", response_model=Payment)
async def create_payment(
        payment_data: PaymentCreate,
        background_tasks: BackgroundTasks,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Create a new payment record
    """
    # Verify tenant belongs to landlord
    tenant = db.query(TenantModel).filter(
        TenantModel.id == payment_data.tenant_id,
        TenantModel.landlord_id == current_landlord.id
    ).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Create payment
    db_payment = PaymentModel(
        landlord_id=current_landlord.id,
        **payment_data.dict()
    )

    # Set initial values
    db_payment.amount_paid = 0
    db_payment.balance = payment_data.amount
    db_payment.status = PaymentStatus.PENDING

    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)

    return db_payment


@router.post("/{payment_id}/process")
async def process_payment(
        payment_id: int,
        amount_paid: float,
        payment_method: PaymentMethod,
        background_tasks: BackgroundTasks,
        transaction_id: str = None,
        mpesa_code: str = None,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Process a payment (mark as paid)
    """
    payment = db.query(PaymentModel).filter(
        PaymentModel.id == payment_id,
        PaymentModel.landlord_id == current_landlord.id
    ).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Update payment
    payment.amount_paid = amount_paid
    payment.balance = payment.amount - amount_paid
    payment.payment_date = datetime.utcnow()
    payment.payment_method = payment_method
    payment.transaction_id = transaction_id
    payment.mpesa_code = mpesa_code

    if payment.balance <= 0:
        payment.status = PaymentStatus.COMPLETED
    elif payment.balance < payment.amount:
        payment.status = PaymentStatus.PARTIAL
    else:
        payment.status = PaymentStatus.PENDING

    db.commit()

    # Generate receipt
    receipt = await generate_receipt(int(payment.id), db)

    # Get tenant info
    tenant = db.query(TenantModel).filter(TenantModel.id == payment.tenant_id).first()

    # Send confirmation SMS
    background_tasks.add_task(
        sms_service.send_payment_confirmation,
        tenant_name=tenant.first_name,
        phone=tenant.phone,
        amount=amount_paid,
        receipt_no=receipt.receipt_number
    )

    # Trigger n8n workflow
    background_tasks.add_task(
        n8n_service.trigger_payment_received,
        {
            'payment_id': payment.id,
            'tenant_id': tenant.id,
            'tenant_name': f"{tenant.first_name} {tenant.last_name}",
            'amount': amount_paid,
            'receipt_number': receipt.receipt_number
        }
    )

    return payment


@router.get("", response_model=List[Payment])
async def list_payments(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db),
        tenant_id: int = None,
        status: PaymentStatus = None,
        skip: int = 0,
        limit: int = 100
):
    """
    List payments
    """
    query = db.query(PaymentModel).filter(
        PaymentModel.landlord_id == current_landlord.id
    )

    if tenant_id:
        query = query.filter(PaymentModel.tenant_id == tenant_id)

    if status:
        query = query.filter(PaymentModel.status == status)

    payments = query.order_by(PaymentModel.created_at.desc()).offset(skip).limit(limit).all()

    # Add tenant names
    for payment in payments:
        tenant = db.query(TenantModel).filter(TenantModel.id == payment.tenant_id).first()
        payment.tenant_name = f"{tenant.first_name} {tenant.last_name}" if tenant else "Unknown"

    return payments


@router.get("/summary", response_model=PaymentSummary)
async def get_payment_summary(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Get payment summary
    """
    summary = accounting_service.get_payment_summary(db, current_landlord.id)
    return summary


@router.get("/overdue")
async def get_overdue_payments(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Get all overdue payments
    """
    overdue = accounting_service.identify_overdue_payments(db, current_landlord.id)

    result = []
    for payment in overdue:
        tenant = db.query(TenantModel).filter(TenantModel.id == payment.tenant_id).first()
        days_overdue = (date.today() - payment.due_date).days

        result.append({
            "payment_id": payment.id,
            "tenant_id": payment.tenant_id,
            "tenant_name": f"{tenant.first_name} {tenant.last_name}",
            "amount": payment.amount,
            "due_date": payment.due_date,
            "days_overdue": days_overdue
        })

    return result


@router.post("/{payment_id}/remind")
async def send_payment_reminder(
        payment_id: int,
        background_tasks: BackgroundTasks,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Send reminder for specific payment
    """
    payment = db.query(PaymentModel).filter(
        PaymentModel.id == payment_id,
        PaymentModel.landlord_id == current_landlord.id
    ).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    tenant = db.query(TenantModel).filter(TenantModel.id == payment.tenant_id).first()

    days_overdue = (date.today() - payment.due_date).days if payment.due_date < date.today() else 0

    if days_overdue > 0:
        background_tasks.add_task(
            sms_service.send_overdue_reminder,
            tenant_name=tenant.first_name,
            phone=tenant.phone,
            amount=payment.balance or payment.amount,
            days_overdue=days_overdue
        )
    else:
        background_tasks.add_task(
            sms_service.send_payment_reminder,
            tenant_name=tenant.first_name,
            phone=tenant.phone,
            amount=payment.amount,
            due_date=payment.due_date.strftime("%Y-%m-%d")
        )

    return {"message": "Reminder sent successfully"}


@router.post("/remind/bulk")
async def send_bulk_reminders(
        property_id: int,
        background_tasks: BackgroundTasks,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Send overdue reminders for all payments belonging to a particular property.
    """
    payments = db.query(PaymentModel).filter(
        PaymentModel.landlord_id == current_landlord.id,
        PaymentModel.property_id == property_id,
        PaymentModel.status == PaymentStatus.OVERDUE
    ).all()

    count = 0
    for payment in payments:
        tenant = db.query(TenantModel).filter(TenantModel.id == payment.tenant_id).first()
        days_overdue = (date.today() - payment.due_date).days if payment.due_date < date.today() else 0
        if tenant:
            background_tasks.add_task(
                sms_service.send_overdue_reminder,
                tenant_name=tenant.first_name,
                phone=tenant.phone,
                amount=payment.balance or payment.amount,
                days_overdue=days_overdue
            )
            # trigger n8n as well
            background_tasks.add_task(
                n8n_service.trigger_overdue_payment,
                {'tenant_id': tenant.id, 'tenant_name': f"{tenant.first_name} {tenant.last_name}"},
                {
                    'payment_id': payment.id,
                    'amount': payment.amount,
                    'due_date': payment.due_date.isoformat()
                },
                days_overdue
            )
            count += 1

    return {"message": "Reminders queued", "count": count}


@router.post("/remind/all-overdue")
async def remind_all_overdue(
        background_tasks: BackgroundTasks,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Send reminders for every overdue payment for the current landlord.
    """
    overdue = accounting_service.identify_overdue_payments(db, current_landlord.id)
    count = 0
    for payment in overdue:
        tenant = db.query(TenantModel).filter(TenantModel.id == payment.tenant_id).first()
        days_overdue = (date.today() - payment.due_date).days if payment.due_date < date.today() else 0
        if tenant:
            background_tasks.add_task(
                sms_service.send_overdue_reminder,
                tenant_name=tenant.first_name,
                phone=tenant.phone,
                amount=payment.balance or payment.amount,
                days_overdue=days_overdue
            )
            background_tasks.add_task(
                n8n_service.trigger_overdue_payment,
                {'tenant_id': tenant.id, 'tenant_name': f"{tenant.first_name} {tenant.last_name}"},
                {
                    'payment_id': payment.id,
                    'amount': payment.amount,
                    'due_date': payment.due_date.isoformat()
                },
                days_overdue
            )
            count += 1
    return {"message": "Reminders queued", "count": count}


@router.get("/receipts", response_model=List[Receipt])
async def list_receipts(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db),
        tenant_id: int = None,
        skip: int = 0,
        limit: int = 100
):
    """
    List all receipts
    """
    query = db.query(ReceiptModel).join(PaymentModel).filter(
        PaymentModel.landlord_id == current_landlord.id
    )

    if tenant_id:
        query = query.filter(PaymentModel.tenant_id == tenant_id)

    receipts = query.order_by(ReceiptModel.created_at.desc()).offset(skip).limit(limit).all()
    return receipts


@router.get("/receipts/{receipt_id}", response_model=Receipt)
async def get_receipt(
        receipt_id: int,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Get receipt by ID
    """
    receipt = db.query(ReceiptModel).filter(ReceiptModel.id == receipt_id).first()

    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    # Verify payment belongs to landlord
    payment = db.query(PaymentModel).filter(
        PaymentModel.id == receipt.payment_id,
        PaymentModel.landlord_id == current_landlord.id
    ).first()

    if not payment:
        raise HTTPException(status_code=403, detail="Not authorized")

    return receipt


async def generate_receipt(payment_id: int, db: Session) -> ReceiptModel:
    """
    Generate receipt for payment
    """
    payment = db.query(PaymentModel).filter(PaymentModel.id == payment_id).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Check if receipt already exists
    existing = db.query(ReceiptModel).filter(ReceiptModel.payment_id == payment_id).first()
    if existing:
        return existing

    # Generate receipt number
    receipt_number = accounting_service.generate_receipt_number()

    # Create receipt
    receipt = ReceiptModel(
        payment_id=payment_id,
        receipt_number=receipt_number
    )

    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    # Update payment
    payment.receipt_number = receipt_number
    payment.receipt_generated = True
    db.commit()

    return receipt