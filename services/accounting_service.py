from typing import Dict, List, Any, Optional
from datetime import datetime, date, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from models.payment import Payment, PaymentStatus
from models.tenant import Tenant


class AccountingService:
    def get_payment_summary(self, db: Session, landlord_id: int) -> Dict[str, Any]:
        """
        Get payment summary for dashboard
        """
        # Total collected (completed payments)
        total_collected = db.query(func.sum(Payment.amount_paid)).filter(
            Payment.landlord_id == landlord_id,
            Payment.status == PaymentStatus.COMPLETED
        ).scalar() or 0

        # Pending payments
        pending = db.query(func.sum(Payment.amount)).filter(
            Payment.landlord_id == landlord_id,
            Payment.status == PaymentStatus.PENDING
        ).scalar() or 0

        # Overdue payments
        today = date.today()
        overdue = db.query(func.sum(Payment.amount)).filter(
            Payment.landlord_id == landlord_id,
            Payment.status == PaymentStatus.OVERDUE
        ).scalar() or 0

        # Monthly total (current month)
        current_month_start = date(today.year, today.month, 1)
        monthly_total = db.query(func.sum(Payment.amount)).filter(
            Payment.landlord_id == landlord_id,
            Payment.status == PaymentStatus.COMPLETED,
            Payment.payment_date >= current_month_start
        ).scalar() or 0

        # Payment counts
        total_payments = db.query(Payment).filter(
            Payment.landlord_id == landlord_id
        ).count()

        pending_payments = db.query(Payment).filter(
            Payment.landlord_id == landlord_id,
            Payment.status == PaymentStatus.PENDING
        ).count()

        overdue_payments = db.query(Payment).filter(
            Payment.landlord_id == landlord_id,
            Payment.status == PaymentStatus.OVERDUE
        ).count()

        return {
            "total_collected": total_collected,
            "pending_amount": pending,
            "overdue_amount": overdue,
            "total_payments": total_payments,
            "pending_payments": pending_payments,
            "overdue_payments": overdue_payments,
            "monthly_total": monthly_total
        }

    def get_recent_payments(self, db: Session, landlord_id: int, limit: int = 10) -> List[Dict]:
        """
        Get recent payments with tenant details
        """
        payments = db.query(Payment).filter(
            Payment.landlord_id == landlord_id
        ).order_by(
            Payment.created_at.desc()
        ).limit(limit).all()

        result = []
        for payment in payments:
            tenant = db.query(Payment, Tenant).join(Tenant, Tenant.id == payment.tenant_id)
            result.append({
                "id": payment.id,
                "tenant_name": f"{tenant.first_name} {tenant.last_name}" if tenant else "Unknown",
                "amount": payment.amount,
                "status": payment.status.value,
                "date": payment.payment_date,
                "due_date": payment.due_date
            })

        return result

    def get_outstanding_balance(self, db: Session, landlord_id: int) -> float:
        """
        Get total outstanding balance
        """
        outstanding = db.query(func.sum(Payment.amount - Payment.amount_paid)).filter(
            Payment.landlord_id == landlord_id,
            Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.OVERDUE])
        ).scalar() or 0

        return outstanding

    def identify_overdue_payments(self, db: Session, landlord_id: int) -> List[Payment]:
        """
        Identify and return overdue payments
        """
        today = date.today()

        # Find payments that are past due date and not completed
        overdue_payments = db.query(Payment).filter(
            Payment.landlord_id == landlord_id,
            Payment.due_date < today,
            Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.PARTIAL])
        ).all()

        # Update status to overdue if not already
        for payment in overdue_payments:
            if payment.status != PaymentStatus.OVERDUE:
                payment.status = PaymentStatus.OVERDUE
                db.add(payment)

        if overdue_payments:
            db.commit()

        return overdue_payments

    def get_tenant_balance(self, db: Session, tenant_id: int) -> float:
        """
        Get current balance for a tenant
        """
        total_due = db.query(func.sum(Payment.amount)).filter(
            Payment.tenant_id == tenant_id,
            Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.OVERDUE])
        ).scalar() or 0

        total_paid = db.query(func.sum(Payment.amount_paid)).filter(
            Payment.tenant_id == tenant_id,
            Payment.status == PaymentStatus.COMPLETED
        ).scalar() or 0

        return total_due - total_paid

    def generate_receipt_number(self) -> str:
        """
        Generate unique receipt number
        """
        import random
        import string

        year = datetime.now(timezone.utc).year
        month = datetime.now(timezone.utc).strftime("%m")
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        return f"RCP-{year}{month}-{random_part}"


accounting_service = AccountingService()