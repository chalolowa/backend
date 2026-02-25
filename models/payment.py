from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Enum, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from core.database import Base


class PaymentStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    OVERDUE = "overdue"
    PARTIAL = "partial"


class PaymentMethod(enum.Enum):
    MPESA = "mpesa"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    CARD = "card"
    USSD = "ussd"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    landlord_id = Column(Integer, ForeignKey("landlords.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)

    # Payment details
    amount = Column(Float, nullable=False)
    amount_paid = Column(Float, default=0)
    balance = Column(Float, default=0)

    # Dates
    due_date = Column(Date, nullable=False)
    payment_date = Column(DateTime)

    # Status
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_method = Column(Enum(PaymentMethod))

    # Transaction details
    transaction_id = Column(String, unique=True, index=True)
    mpesa_code = Column(String, index=True)
    reference = Column(String)
    notes = Column(String)

    # Receipt
    receipt_number = Column(String, unique=True)
    receipt_generated = Column(Boolean, default=False)
    receipt_url = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    landlord = relationship("Landlord", back_populates="payments")
    tenant = relationship("Tenant", back_populates="payments")
    property = relationship("Property", back_populates="payments")


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    receipt_number = Column(String, unique=True, nullable=False)

    # Receipt details
    pdf_url = Column(String)
    sent_to_tenant = Column(Boolean, default=False)
    sent_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    payment = relationship("Payment")