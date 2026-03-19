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
from app.services.scheduling import (
    SUPPORTED_BODY_PARTS,
    find_next_slot_from_doctor_availabilities,
    get_doctor_availabilities,
    list_specialty_slots,
    list_top_slot_options,
    map_body_part_to_specialty,
)
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


def create_booking(payload: IntakeRequest, session: dict, selected_slot: dict | None = None):
    doctor_availabilities = session.get("doctor_availabilities") or get_doctor_availabilities(payload.body_part)
    appointment = selected_slot or find_next_slot_from_doctor_availabilities(doctor_availabilities)
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
    session["doctor_availabilities"] = doctor_availabilities
    session.pop("proposed_slots", None)
    session.setdefault("chat_history", [])
    session_store[payload.phone] = session

    return {
        **appointment,
        "email_confirmation": email_status,
        "sms_confirmation": sms_status,
    }


def build_slot_options_prompt(doctor_availabilities: list[dict]) -> tuple[str, list[dict]]:
    slot_options = list_top_slot_options(doctor_availabilities)
    if not slot_options:
        return (
            "I could not find open appointment slots for that specialty yet. Please choose a different body area or request a phone handoff.",
            [],
        )

    lines = []
    normalized_slots = []
    for index, slot in enumerate(slot_options, start=1):
        scheduled_for = datetime.strptime(f"{slot['date']} {slot['time']}", "%Y-%m-%d %H:%M")
        normalized_slot = {
            **slot,
            "scheduled_for": scheduled_for,
        }
        normalized_slots.append(normalized_slot)
        lines.append(
            f"{index}. {scheduled_for.strftime('%b %d, %Y at %I:%M %p')} with {slot['doctor_name']} at {slot['location']}"
        )

    prompt = "I found these available appointments. Reply with the option number you want to book:\n" + "\n".join(lines)
    return prompt, normalized_slots


def select_proposed_slot(message: str, proposed_slots: list[dict]) -> dict | None:
    lowered = message.strip().lower()
    if not proposed_slots:
        return None

    if lowered.isdigit():
        index = int(lowered) - 1
        if 0 <= index < len(proposed_slots):
            return proposed_slots[index]

    for slot in proposed_slots:
        slot_time = slot["scheduled_for"].strftime('%b %d, %Y at %I:%M %p').lower()
        if slot_time in lowered or slot["doctor_name"].lower() in lowered:
            return slot
    return None


def unsupported_body_part_prompt(body_part: str) -> str:
    routing = map_body_part_to_specialty(body_part)
    requested_specialty = routing.get("requested_specialty") or body_part
    supported_examples = ", ".join(SUPPORTED_BODY_PARTS)
    return (
        f"A doctor for {requested_specialty} is not available right now. "
        f"How else can I help? You can also choose one of our available specialties: {supported_examples}."
    )


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
    body_part = session["intake"].get("body_part")
    if body_part:
        session["doctor_availabilities"] = get_doctor_availabilities(body_part)
    phone = session["intake"].get("phone")
    if phone:
        session_store[phone] = session

    booking_completed = False
    selected_slot = select_proposed_slot(payload.message, session.get("proposed_slots", []))

    if selected_slot and not session.get("appointment"):
        booking = create_booking(IntakeRequest(**session["intake"]), session, selected_slot=selected_slot)
        answer = (
            f"Your appointment is confirmed with {booking['doctor_name']} in {booking['specialty']} on "
            f"{booking['scheduled_for'].strftime('%b %d, %Y at %I:%M %p')} at {booking['location']}. "
            f"{booking['email_confirmation']} {booking['sms_confirmation']}"
        )
        booking_completed = True
    elif not missing_intake_fields(session["intake"]) and not session.get("appointment"):
        if not session.get("doctor_availabilities"):
            session.pop("proposed_slots", None)
            answer = unsupported_body_part_prompt(session["intake"].get("body_part", "that request"))
        elif session.get("proposed_slots"):
            answer = "Please choose one of the available appointment options by replying with its number."
        else:
            answer, session["proposed_slots"] = build_slot_options_prompt(session["doctor_availabilities"])
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
        "doctor_availabilities": session.get("doctor_availabilities", []),
        "proposed_slots": session.get("proposed_slots", []),
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
            "doctor_availabilities": [],
            "proposed_slots": [],
        }
        session_store[payload.phone] = session

    if payload.doctor_availabilities:
        session["doctor_availabilities"] = [item.model_dump(mode="json") for item in payload.doctor_availabilities]
    if payload.proposed_slots:
        session["proposed_slots"] = [item.model_dump(mode="json") for item in payload.proposed_slots]

    intake = session.get("intake", {})
    if not session.get("doctor_availabilities") and intake.get("body_part"):
        session["doctor_availabilities"] = get_doctor_availabilities(intake["body_part"])

    phone = intake.get("phone") or payload.phone or payload.session_id
    if not phone:
        raise HTTPException(status_code=400, detail="No phone number available for call handoff.")

    result = await voice_service.start_call(phone, session)
    return result


app.mount("/app/static", StaticFiles(directory="app/static"), name="static")
