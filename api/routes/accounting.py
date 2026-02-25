from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime, date, timedelta
from core.database import get_db
from api.deps import get_current_landlord
from services.accounting_service import accounting_service
from models.payment import Payment as PaymentModel, PaymentStatus
from models.tenant import Tenant as TenantModel

router = APIRouter(prefix="/accounting", tags=["Accounting"])


@router.get("/dashboard")
async def get_accounting_dashboard(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Get accounting dashboard data
    """
    # Get payment summary
    summary = accounting_service.get_payment_summary(db, current_landlord.id)

    # Get recent payments
    recent_payments = accounting_service.get_recent_payments(db, current_landlord.id, 10)

    # Get overdue payments
    overdue = accounting_service.identify_overdue_payments(db, current_landlord.id)

    # Get monthly trend (last 6 months)
    monthly_trend = []
    for i in range(5, -1, -1):
        month_start = date.today().replace(day=1) - timedelta(days=30 * i)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        total = db.query(PaymentModel).filter(
            PaymentModel.landlord_id == current_landlord.id,
            PaymentModel.status == PaymentStatus.COMPLETED,
            PaymentModel.payment_date >= month_start,
            PaymentModel.payment_date <= month_end
        ).count()

        amount = db.query(PaymentModel).filter(
            PaymentModel.landlord_id == current_landlord.id,
            PaymentModel.status == PaymentStatus.COMPLETED,
            PaymentModel.payment_date >= month_start,
            PaymentModel.payment_date <= month_end
        ).with_entities(PaymentModel.amount).all()

        monthly_trend.append({
            "month": month_start.strftime("%B %Y"),
            "payments": total,
            "total": sum(a[0] for a in amount)
        })

    return {
        "summary": summary,
        "recent_payments": recent_payments,
        "overdue_count": len(overdue),
        "overdue_total": sum(p.amount for p in overdue),
        "monthly_trend": monthly_trend
    }


@router.get("/income-statement")
async def get_income_statement(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db),
        year: int = None,
        month: int = None
):
    """
    Get income statement for specified period
    """
    if not year:
        year = date.today().year

    query = db.query(PaymentModel).filter(
        PaymentModel.landlord_id == current_landlord.id,
        PaymentModel.status == PaymentStatus.COMPLETED
    )

    if month:
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        query = query.filter(
            PaymentModel.payment_date >= start_date,
            PaymentModel.payment_date <= end_date
        )
    else:
        query = query.filter(PaymentModel.payment_date >= date(year, 1, 1))

    payments = query.all()

    total_income = sum(p.amount for p in payments)

    # Group by property
    by_property = {}
    for payment in payments:
        prop_id = payment.property_id
        if prop_id not in by_property:
            by_property[prop_id] = {
                "property_id": prop_id,
                "property_name": payment.property.name if payment.property else "Unknown",
                "total": 0,
                "payments": 0
            }
        by_property[prop_id]["total"] += payment.amount
        by_property[prop_id]["payments"] += 1

    return {
        "period": f"{year}-{month:02d}" if month else str(year),
        "total_income": total_income,
        "total_payments": len(payments),
        "by_property": list(by_property.values())
    }


@router.get("/tenant-balances")
async def get_all_tenant_balances(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Get balances for all tenants
    """
    tenants = db.query(TenantModel).filter(
        TenantModel.landlord_id == current_landlord.id,
        TenantModel.is_active == True
    ).all()

    result = []
    for tenant in tenants:
        balance = accounting_service.get_tenant_balance(db, tenant.id)
        if balance > 0:
            result.append({
                "tenant_id": tenant.id,
                "tenant_name": f"{tenant.first_name} {tenant.last_name}",
                "phone": tenant.phone,
                "balance": balance,
                "property_id": tenant.property_id,
                "unit_id": tenant.unit_id
            })

    return result


@router.post("/reconcile")
async def reconcile_payments(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Reconcile payments and update overdue status
    """
    overdue = accounting_service.identify_overdue_payments(db, current_landlord.id)

    return {
        "message": f"Reconciled {len(overdue)} overdue payments",
        "overdue_count": len(overdue)
    }