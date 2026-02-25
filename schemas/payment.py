from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from enum import Enum

class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    OVERDUE = "overdue"
    PARTIAL = "partial"


class PaymentMethod(str, Enum):
    MPESA = "mpesa"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    CARD = "card"
    USSD = "ussd"


class PaymentBase(BaseModel):
    amount: float
    due_date: date
    notes: Optional[str] = None


class PaymentCreate(PaymentBase):
    tenant_id: int
    property_id: int
    payment_method: Optional[PaymentMethod] = None
    mpesa_code: Optional[str] = None
    transaction_id: Optional[str] = None


class PaymentUpdate(BaseModel):
    status: Optional[PaymentStatus] = None
    amount_paid: Optional[float] = None
    payment_date: Optional[datetime] = None
    payment_method: Optional[PaymentMethod] = None
    transaction_id: Optional[str] = None
    mpesa_code: Optional[str] = None


class Payment(PaymentBase):
    id: int
    landlord_id: int
    tenant_id: int
    property_id: int
    amount_paid: float
    balance: float
    payment_date: Optional[datetime]
    status: PaymentStatus
    payment_method: Optional[PaymentMethod]
    transaction_id: Optional[str]
    mpesa_code: Optional[str]
    receipt_number: Optional[str]
    receipt_generated: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaymentDetail(Payment):
    tenant_name: str
    property_name: str
    unit_number: Optional[str]


class ReceiptBase(BaseModel):
    payment_id: int


class ReceiptCreate(ReceiptBase):
    receipt_number: str
    pdf_url: Optional[str] = None


class Receipt(ReceiptBase):
    id: int
    receipt_number: str
    pdf_url: Optional[str]
    sent_to_tenant: bool
    sent_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentSummary(BaseModel):
    total_collected: float
    pending_amount: float
    overdue_amount: float
    total_payments: int
    pending_payments: int
    overdue_payments: int
    monthly_total: float
    yearly_total: float