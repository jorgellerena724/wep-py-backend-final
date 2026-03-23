from datetime import datetime
from sqlmodel import Field, SQLModel, Column
from sqlalchemy.dialects.postgresql import JSONB
from typing import Any, Optional, Dict

class BookingEvents(SQLModel, table=True):
    __tablename__ = "bookings_events"

    access_code: str = Field(primary_key=True, index=True, max_length=10)

    # Cal.com identifiers
    cal_booking_id: int = Field(index=True)
    cal_booking_uid: Optional[str] = Field(default=None, index=True, max_length=255)  # UID que usa Cal.com internamente
    
    # Reschedule tracking
    rescheduled_from_uid: Optional[str] = Field(default=None, max_length=255)  # UID del booking original al reagendar
    cancellation_reason: Optional[str] = Field(default=None, max_length=500)

    # Stripe
    stripe_payment_id: Optional[str] = Field(default=None, index=True)
    stripe_refund_id: Optional[str] = Field(default=None, index=True)      # Para cuando implementes reembolsos

    # Tiempo
    scheduled_at: datetime = Field(index=True)
    rescheduled_at: Optional[datetime] = Field(default=None)               # Cuándo se reagendó
    cancelled_at: Optional[datetime] = Field(default=None)

    # Estado y montos
    status: str = Field(default="scheduled")  # scheduled | cancelled | rescheduled
    total_amount: float = Field(default=0.0)
    discount_applied: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB)
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True  