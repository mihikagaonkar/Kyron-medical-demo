from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class IntakeRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    dob: date
    phone: str = Field(min_length=7, max_length=20)
    email: EmailStr
    reason: str = Field(min_length=3, max_length=300)
    body_part: str = Field(min_length=2, max_length=80)
    sms_opt_in: bool = False


class AppointmentResponse(BaseModel):
    appointment_id: str
    doctor_name: str
    specialty: str
    scheduled_for: datetime
    location: str
    email_confirmation: str
    sms_confirmation: str


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=1000)
    sms_opt_in: bool | None = None


class ChatResponse(BaseModel):
    response: str
    phone: str | None = None
    booking_completed: bool = False


class SwitchToPhoneRequest(BaseModel):
    session_id: str
    phone: str | None = None


class SwitchToPhoneResponse(BaseModel):
    call_status: str
    provider: str
    call_reference: str | None = None
    detail: str


class AvailabilitySlot(BaseModel):
    doctor_name: str
    specialty: str
    date: date
    time: str
    location: str
