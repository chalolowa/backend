from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class LandlordBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    company_name: Optional[str] = None
    tax_id: Optional[str] = None
    business_address: Optional[str] = None


class LandlordCreate(LandlordBase):
    auth_provider_id: str  # from frontend auth (Firebase, Clerk, etc.)


class LandlordUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    tax_id: Optional[str] = None
    business_address: Optional[str] = None
    notification_email: Optional[bool] = None
    notification_sms: Optional[bool] = None


class Landlord(LandlordBase):
    id: int
    auth_provider_id: str
    is_active: bool
    notification_email: bool
    notification_sms: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True