from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.models import (
    IntakeRequest,
    AppointmentResponse,
    ChatRequest,
    ChatResponse,
    SwitchToPhoneRequest,
    SwitchToPhoneResponse,
    AvailabilitySlot,
)
from app.services.chat_intake import build_missing_fields_prompt, missing_intake_fields, update_intake_from_message
from app.services.scheduling import find_next_slot, list_specialty_slots
from app.services.ai import AIService
from app.services.voice import VoiceService
from app.services.notifications import NotificationService

app = FastAPI(title="Kyron Medical AI Patient Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ai_service = AIService()
voice_service = VoiceService()
notification_service = NotificationService()

session_store: dict[str, dict] = {}


def create_booking(payload: IntakeRequest, session: dict):
    appointment = find_next_slot(payload.body_part)
    confirmation_text = (
        f"Hi {payload.full_name}, your appointment is booked with {appointment['doctor_name']} "
        f"({appointment['specialty']}) on {appointment['scheduled_for'].strftime('%b %d, %Y at %I:%M %p')} "
        f"at {appointment['location']}."
    )

    email_status = notification_service.send_email_confirmation(payload.email, confirmation_text)
    sms_status = notification_service.send_sms_confirmation(
        payload.phone,
        confirmation_text,
        payload.sms_opt_in,
    )

    session["intake"] = payload.model_dump(mode="json")
    session["appointment"] = {
        **appointment,
        "scheduled_for": appointment["scheduled_for"].isoformat(),
    }
    session.setdefault("chat_history", [])
    session_store[payload.phone] = session

    return {
        **appointment,
        "email_confirmation": email_status,
        "sms_confirmation": sms_status,
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}



@app.get("/", include_in_schema=False)
def index():
    return FileResponse("app/static/index.html")


@app.get("/api/availability", response_model=list[AvailabilitySlot])
def availability(body_part: str):
    return list_specialty_slots(body_part)


@app.post("/api/intake_schedule", response_model=AppointmentResponse)
def intake_schedule(payload: IntakeRequest):
    session = session_store.get(payload.phone) or {"intake": {}, "appointment": {}, "chat_history": []}
    return create_booking(payload, session)


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    session = session_store.get(payload.session_id)
    if not session:
        session = {"intake": {"sms_opt_in": False}, "appointment": {}, "chat_history": []}
        session_store[payload.session_id] = session

    previous_intake = dict(session.get("intake", {}))
    session["intake"] = update_intake_from_message(session.get("intake", {}), payload.message)
    if payload.sms_opt_in is not None:
        session["intake"]["sms_opt_in"] = payload.sms_opt_in
    phone = session["intake"].get("phone")
    if phone:
        session_store[phone] = session

    booking_completed = False

    if not missing_intake_fields(session["intake"]) and not session.get("appointment"):
        booking = create_booking(IntakeRequest(**session["intake"]), session)
        answer = (
            f"Your appointment is confirmed with {booking['doctor_name']} in {booking['specialty']} on "
            f"{booking['scheduled_for'].strftime('%b %d, %Y at %I:%M %p')} at {booking['location']}. "
            f"{booking['email_confirmation']} {booking['sms_confirmation']}"
        )
        booking_completed = True
    elif session.get("appointment"):
        answer = ai_service.generate(payload.message, session["chat_history"], session)
    else:
        answer = build_missing_fields_prompt(session["intake"], previous_intake)

    session["chat_history"].append({"role": "user", "content": payload.message})
    session["chat_history"].append({"role": "assistant", "content": answer})
    session["chat_history"] = session["chat_history"][-10:]
    return {
        "response": answer,
        "phone": phone,
        "booking_completed": booking_completed,
    }


@app.post("/api/switch-to-phone", response_model=SwitchToPhoneResponse)
async def switch_to_phone(payload: SwitchToPhoneRequest):
    session = session_store.get(payload.session_id)
    if not session and payload.phone:
        session = session_store.get(payload.phone)

    if not session:
        if not payload.phone:
            raise HTTPException(status_code=404, detail="Session not found for phone handoff.")
        session = {
            "intake": {"phone": payload.phone},
            "appointment": {},
            "chat_history": [],
        }
        session_store[payload.phone] = session

    intake = session.get("intake", {})
    phone = intake.get("phone") or payload.phone or payload.session_id
    if not phone:
        raise HTTPException(status_code=400, detail="No phone number available for call handoff.")

    result = await voice_service.start_call(phone, session)
    return result


app.mount("/app/static", StaticFiles(directory="app/static"), name="static")
