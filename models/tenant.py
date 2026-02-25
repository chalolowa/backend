from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Date, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    landlord_id = Column(Integer, ForeignKey("landlords.id"), nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=True)

    # Personal info
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, index=True)
    phone = Column(String, nullable=False, unique=True, index=True)
    alternative_phone = Column(String)

    # Identification
    id_type = Column(String, default="national_id")
    id_number = Column(String)

    # Lease details
    lease_start = Column(Date, nullable=False)
    lease_end = Column(Date, nullable=False)
    monthly_rent = Column(Float, nullable=False)
    security_deposit = Column(Float)
    deposit_paid = Column(Boolean, default=False)

    # Payment settings
    rent_due_day = Column(Integer, default=1)  # Day of month rent is due
    payment_method = Column(String, default="mpesa")  # mpesa, bank, cash

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Emergency contact
    emergency_contact_name = Column(String)
    emergency_contact_phone = Column(String)
    emergency_contact_relationship = Column(String)

    # Additional data
    metadata_json = Column('metadata', JSON, default={})

    # Relationships
    landlord = relationship("Landlord", back_populates="tenants")
    property = relationship("Property", back_populates="tenants")
    unit = relationship("Unit", back_populates="tenant")
    payments = relationship("Payment", back_populates="tenant")
    reminders = relationship("Reminder", back_populates="tenant")
    issues = relationship("Issue", back_populates="tenant")


class Issue(Base):
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)

    # Issue details
    category = Column(String, nullable=False)  # electrical, water, financial, garbage, other
    description = Column(String)
    priority = Column(String, default="medium")  # low, medium, high, urgent
    status = Column(String, default="open")  # open, in_progress, resolved, closed

    # Resolution
    resolution_notes = Column(String)
    resolved_at = Column(DateTime)
    resolved_by = Column(String)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    tenant = relationship("Tenant", back_populates="issues")