from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from core.database import Base

class Landlord(Base):
    __tablename__ = "landlords"

    id = Column(Integer, primary_key=True, index=True)

    # ID from frontend auth provider (Firebase, Supabase, Clerk, etc.)
    auth_provider_id = Column(String, unique=True, index=True, nullable=False)

    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String, unique=True, index=True)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Company info
    company_name = Column(String)
    tax_id = Column(String)
    business_address = Column(String)

    # Notification Settings
    notification_email = Column(Boolean, default=True)
    notification_sms = Column(Boolean, default=True)

    # Relationships
    properties = relationship("Property", back_populates="landlord", cascade="all, delete-orphan")
    tenants = relationship("Tenant", back_populates="landlord", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="landlord")