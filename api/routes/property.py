from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from core.database import get_db
from models.property import Property as PropertyModel, Unit as UnitModel
from models.tenant import Tenant as TenantModel
from schemas.property import Property, PropertyCreate, PropertyUpdate, Unit, UnitCreate, PropertyDetail
from api.deps import get_current_landlord

router = APIRouter(prefix="/properties", tags=["Properties"])


@router.post("", response_model=Property)
async def create_property(
        property_data: PropertyCreate,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Create a new property
    """
    # Create property
    db_property = PropertyModel(
        landlord_id=current_landlord.id,
        **property_data.dict(exclude={'units'})
    )
    db.add(db_property)
    db.flush()

    # Create units if provided
    if property_data.units:
        for unit_data in property_data.units:
            db_unit = UnitModel(
                property_id=db_property.id,
                **unit_data.dict()
            )
            db.add(db_unit)

    db.commit()
    db.refresh(db_property)

    # Calculate totals
    db_property.monthly_rent_total = sum(u.monthly_rent for u in db_property.units)
    db.commit()

    return db_property


@router.get("", response_model=List[PropertyDetail])
async def list_properties(
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db),
        skip: int = 0,
        limit: int = 100
):
    """
    List all properties for current landlord; include occupancy information.
    """
    properties = db.query(PropertyModel).filter(
        PropertyModel.landlord_id == current_landlord.id
    ).offset(skip).limit(limit).all()

    # Return properties as-is; the Pydantic response_model will compute
    # occupied_units, available_units, and occupancy_rate using validators
    return properties


@router.get("/{property_id}", response_model=PropertyDetail)
async def get_property(
        property_id: int,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Get property by ID
    """
    property = db.query(PropertyModel).filter(
        PropertyModel.id == property_id,
        PropertyModel.landlord_id == current_landlord.id
    ).first()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Return the property; Pydantic validators in PropertyDetail will
    # compute occupied_units, available_units, and occupancy_rate
    return property


@router.put("/{property_id}", response_model=Property)
async def update_property(
        property_id: int,
        property_update: PropertyUpdate,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Update property
    """
    property = db.query(PropertyModel).filter(
        PropertyModel.id == property_id,
        PropertyModel.landlord_id == current_landlord.id
    ).first()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    for key, value in property_update.dict(exclude_unset=True).items():
        setattr(property, key, value)

    db.commit()
    db.refresh(property)
    return property


@router.delete("/{property_id}")
async def delete_property(
        property_id: int,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Delete property
    """
    property = db.query(PropertyModel).filter(
        PropertyModel.id == property_id,
        PropertyModel.landlord_id == current_landlord.id
    ).first()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Check if property has tenants
    tenants = db.query(TenantModel).filter(TenantModel.property_id == property_id).first()
    if tenants:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete property with existing tenants"
        )

    db.delete(property)
    db.commit()

    return {"message": "Property deleted successfully"}


# Unit endpoints
@router.post("/{property_id}/units", response_model=Unit)
async def create_unit(
        property_id: int,
        unit_data: UnitCreate,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Add unit to property
    """
    # Verify property belongs to landlord
    property = db.query(PropertyModel).filter(
        PropertyModel.id == property_id,
        PropertyModel.landlord_id == current_landlord.id
    ).first()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Create unit
    db_unit = UnitModel(
        property_id=property_id,
        **unit_data.dict()
    )
    db.add(db_unit)
    db.commit()
    db.refresh(db_unit)

    # Update property total units and rent
    property.total_units += 1
    property.monthly_rent_total += unit_data.monthly_rent
    db.commit()

    return db_unit


@router.put("/units/{unit_id}", response_model=Unit)
async def update_unit(
        unit_id: int,
        unit_update: dict,
        current_landlord=Depends(get_current_landlord),
        db: Session = Depends(get_db)
):
    """
    Update unit
    """
    unit = db.query(UnitModel).filter(UnitModel.id == unit_id).first()

    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    # Verify property belongs to landlord
    property = db.query(PropertyModel).filter(
        PropertyModel.id == unit.property_id,
        PropertyModel.landlord_id == current_landlord.id
    ).first()

    if not property:
        raise HTTPException(status_code=403, detail="Not authorized")

    for key, value in unit_update.items():
        setattr(unit, key, value)

    db.commit()
    db.refresh(unit)
    return unit