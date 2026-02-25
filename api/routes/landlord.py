from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.database import get_db
from models.landlord import Landlord as LandlordModel
from api.deps import get_current_landlord

router = APIRouter(prefix="/landlords", tags=["Landlords"])


@router.get("/dashboard/stats")
async def get_dashboard_stats(
        current_landlord: LandlordModel = Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Get dashboard statistics
    """
    from services.accounting_service import accounting_service

    # Get property stats
    properties = current_landlord.properties
    total_properties = len(properties)
    total_units = sum(p.total_units for p in properties)
    occupied_units = sum(p.occupied_units for p in properties)

    # Get tenant stats
    tenants = current_landlord.tenants
    active_tenants = len([t for t in tenants if t.is_active])

    # Get payment summary
    payment_summary = accounting_service.get_payment_summary(db, current_landlord.id)

    # Get overdue payments
    overdue_payments = accounting_service.identify_overdue_payments(db, current_landlord.id)

    return {
        "properties": {
            "total": total_properties,
            "total_units": total_units,
            "occupied_units": occupied_units,
            "occupancy_rate": (occupied_units / total_units * 100) if total_units > 0 else 0
        },
        "tenants": {
            "total": len(tenants),
            "active": active_tenants
        },
        "payments": payment_summary,
        "overdue_count": len(overdue_payments)
    }