from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class UnitBase(BaseModel):
    unit_number: str
    bedroom_count: Optional[int] = None
    bathroom_count: Optional[int] = None
    square_feet: Optional[float] = None
    monthly_rent: float
    security_deposit: Optional[float] = None
    status: str = "available"


class UnitCreate(UnitBase):
    pass


class UnitUpdate(BaseModel):
    unit_number: Optional[str] = None
    monthly_rent: Optional[float] = None
    status: Optional[str] = None
    is_occupied: Optional[bool] = None


class Unit(UnitBase):
    id: int
    property_id: int
    is_occupied: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PropertyBase(BaseModel):
    name: str
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "Kenya"
    total_units: int = 1
    property_type: Optional[str] = None
    year_built: Optional[int] = None


class PropertyCreate(PropertyBase):
    units: List[UnitCreate] = Field(default_factory=list)

class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None


class Property(PropertyBase):
    id: int
    landlord_id: int
    monthly_rent_total: float
    deposit_total: float
    is_active: bool
    created_at: datetime
    updated_at: datetime
    units: List[Unit] = Field(default_factory=list)

    class Config:
        from_attributes = True


class PropertyDetail(Property):
    occupied_units: int = 0
    available_units: int = 0
    occupancy_rate: float = 0
    total_tenants: int = 0