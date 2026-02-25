from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date, datetime

class TenantBase(BaseModel):
    first_name: str
    last_name: str
    email: Optional[EmailStr] = None
    phone: str
    alternative_phone: Optional[str] = None
    id_type: str = "national_id"
    id_number: Optional[str] = None
    monthly_rent: float
    rent_due_day: int = 1


class TenantCreate(TenantBase):
    property_id: int
    unit_id: Optional[int] = None
    lease_start: date
    lease_end: date
    security_deposit: Optional[float] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None


class TenantUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    monthly_rent: Optional[float] = None
    is_active: Optional[bool] = None


class Tenant(TenantBase):
    id: int
    landlord_id: int
    property_id: int
    unit_id: Optional[int]
    lease_start: date
    lease_end: date
    security_deposit: Optional[float]
    deposit_paid: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    emergency_contact_name: Optional[str]
    emergency_contact_phone: Optional[str]
    emergency_contact_relationship: Optional[str]

    class Config:
        from_attributes = True


class TenantDetail(Tenant):
    property_name: Optional[str]
    unit_number: Optional[str]
    balance: float = 0
    last_payment_date: Optional[datetime]
    last_payment_amount: Optional[float]
    next_payment_date: Optional[date]


class IssueBase(BaseModel):
    category: str
    description: Optional[str] = None
    priority: str = "medium"


class IssueCreate(IssueBase):
    tenant_id: int


class Issue(IssueBase):
    id: int
    tenant_id: int
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True