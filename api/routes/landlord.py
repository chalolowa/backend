from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from core.database import get_db
from models.landlord import Landlord as LandlordModel
from api.deps import get_current_landlord
from schemas.landlord import LandlordCreate, Landlord


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
    # use the hybrid property added to Property model; it performs the same
    # calculation and keeps all logic in one place.
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


# additional endpoints for landlord registration and profiling
@router.post("", response_model=Landlord)
async def create_landlord(
        landlord_data: LandlordCreate,
        db: Session = Depends(get_db)
):
    """
    Create or return an existing landlord based on auth_provider_id.
    """
    existing = db.query(LandlordModel).filter(
        LandlordModel.auth_provider_id == landlord_data.auth_provider_id
    ).first()
    if existing:
        return existing

    new_landlord = LandlordModel(
        auth_provider_id=landlord_data.auth_provider_id,
        email=landlord_data.email,
        full_name=landlord_data.full_name,
        phone=landlord_data.phone,
        company_name=landlord_data.company_name,
        tax_id=landlord_data.tax_id,
        business_address=landlord_data.business_address
    )
    db.add(new_landlord)
    db.commit()
    db.refresh(new_landlord)
    return new_landlord


@router.get("/me", response_model=Landlord)
async def get_my_profile(
        current_landlord: LandlordModel = Depends(get_current_landlord)
):
    """
    Return current landlord profile.
    """
    return current_landlord