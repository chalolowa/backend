from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from core.database import Base


class ReminderType(enum.Enum):
    PAYMENT = "payment"
    LEASE_EXPIRY = "lease_expiry"
    MAINTENANCE = "maintenance"
    GENERAL = "general"
    UPCOMING = "upcoming"
    OVERDUE = "overdue"


class ReminderStatus(enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    landlord_id = Column(Integer, ForeignKey("landlords.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)

    # Reminder details
    reminder_type = Column(Enum(ReminderType), nullable=False)
    message = Column(String, nullable=False)

    # Delivery
    delivery_method = Column(String)  # sms, email, both
    scheduled_for = Column(DateTime)
    sent_at = Column(DateTime)
    status = Column(Enum(ReminderStatus), default=ReminderStatus.PENDING)

    # Africa's Talking reference
    at_message_id = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    landlord = relationship("Landlord")
    tenant = relationship("Tenant", back_populates="reminders")