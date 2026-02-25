from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from core.database import Base

class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    landlord_id = Column(Integer, ForeignKey("landlords.id"), nullable=False)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    city = Column(String)
    state = Column(String)
    country = Column(String, default="Kenya")

    # Property details
    total_units = Column(Integer, default=1)
    property_type = Column(String)  # apartment, house, commercial
    year_built = Column(Integer)

    # Financial
    monthly_rent_total = Column(Float, default=0)
    deposit_total = Column(Float, default=0)

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Additional data
    metadata_json = Column('metadata', JSON, default={})

    # Relationships
    landlord = relationship("Landlord", back_populates="properties")
    units = relationship("Unit", back_populates="property", cascade="all, delete-orphan")
    tenants = relationship("Tenant", back_populates="property")
    payments = relationship("Payment", back_populates="property")


class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    unit_number = Column(String, nullable=False)

    # Unit details
    bedroom_count = Column(Integer)
    bathroom_count = Column(Integer)
    square_feet = Column(Float)

    # Financial
    monthly_rent = Column(Float, nullable=False)
    security_deposit = Column(Float)

    # Status
    is_occupied = Column(Boolean, default=False)
    status = Column(String, default="available")  # available, occupied, maintenance

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    property = relationship("Property", back_populates="units")
    tenant = relationship("Tenant", back_populates="unit", uselist=False)