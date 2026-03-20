import json
from datetime import date, datetime, timedelta
from functools import lru_cache
import uuid

from openai import OpenAI

from app.config import settings

DOCTORS = [
    {
        "name": "Dr. Maya Patel",
        "specialty": "Orthopedics",
        "location": "Kyron Medical - Downtown",
        "days": {1, 3},  # Tue, Thu
    },
    {
        "name": "Dr. Ethan Brooks",
        "specialty": "Cardiology",
        "location": "Kyron Medical - West Campus",
        "days": {0, 2},  # Mon, Wed
    },
    {
        "name": "Dr. Leila Hassan",
        "specialty": "Neurology",
        "location": "Kyron Medical - Downtown",
        "days": {1, 4},  # Tue, Fri
    },
    {
        "name": "Dr. Jonah Reeves",
        "specialty": "Pulmonology",
        "location": "Kyron Medical - North Campus",
        "days": {2, 4},  # Wed, Fri
    },
    {
        "name": "Dr. Sofia Nguyen",
        "specialty": "Dermatology",
        "location": "Kyron Medical - East Campus",
        "days": {0, 3},  # Mon, Thu
    },
]

TIME_SLOTS = ["09:00", "10:30", "13:00", "15:30"]

AVAILABLE_SPECIALTIES = tuple(sorted({doctor["specialty"] for doctor in DOCTORS}))
SUPPORTED_BODY_PARTS = AVAILABLE_SPECIALTIES

_routing_client = (
    OpenAI(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    if settings.groq_api_key
    else None
)


@lru_cache(maxsize=256)
def map_body_part_to_specialty(body_part: str) -> dict:
    normalized_body_part = " ".join(body_part.strip().split())
    if not normalized_body_part:
        return {
            "matched_specialty": None,
            "requested_specialty": None,
            "available": False,
        }

    if not _routing_client:
        return {
            "matched_specialty": None,
            "requested_specialty": None,
            "available": False,
        }

    specialty_list = ", ".join(AVAILABLE_SPECIALTIES)
    messages = [
        {
            "role": "system",
            "content": (
                "You route patient scheduling requests to medical specialties. "
                f"Available specialties in this clinic are: {specialty_list}. "
                "Given a body part, symptom description, or ailment, decide whether it maps to one of those available specialties. "
                "Return strict JSON with keys matched_specialty, requested_specialty, and available. "
                "Set matched_specialty to one of the available specialties only when there is a clear match. "
                "Set requested_specialty to the best specialty name you infer from the request, even if unavailable. "
                "Set available to true only if matched_specialty is one of the listed available specialties. "
                "If there is no appropriate available specialty, set matched_specialty to null and available to false."
            ),
        },
        {
            "role": "user",
            "content": normalized_body_part,
        },
    ]

    try:
        response = _routing_client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
    except Exception:
        return {
            "matched_specialty": None,
            "requested_specialty": None,
            "available": False,
        }

    matched_specialty = parsed.get("matched_specialty")
    requested_specialty = parsed.get("requested_specialty")
    available = bool(parsed.get("available")) and matched_specialty in AVAILABLE_SPECIALTIES

    return {
        "matched_specialty": matched_specialty if available else None,
        "requested_specialty": requested_specialty or matched_specialty,
        "available": available,
    }


def infer_specialty(body_part: str) -> str | None:
    return map_body_part_to_specialty(body_part)["matched_specialty"]


def build_availability_window(num_days: int = 60):
    start_date = date.today() +timedelta(days=1)

    
    doctor_availabilities = []

    for doctor in DOCTORS:
        slots = []

        for i in range(num_days):
            current = start_date + timedelta(days=i)

            if current.weekday() in doctor["days"]:
                for time_slot in TIME_SLOTS:
                    slots.append(f"{current.isoformat()} {time_slot}")

        doctor_availabilities.append(
            {
                "doctor": doctor["name"],
                "specialty": doctor["specialty"],
                "location": doctor["location"],
                "slots": slots,
            }
        )

    return doctor_availabilities


AVAILABILITY = build_availability_window()


def get_doctor_availabilities(body_part: str):
    specialty = infer_specialty(body_part)
    if not specialty:
        return []
    candidates = [doctor for doctor in AVAILABILITY if doctor["specialty"] == specialty]
    return candidates


def flatten_doctor_availabilities(doctor_availabilities: list[dict]):
    flattened = []
    for doctor in doctor_availabilities:
        for slot in doctor.get("slots", []):
            slot_date, slot_time = slot.split(" ", 1)
            flattened.append(
                {
                    "doctor_name": doctor["doctor"],
                    "specialty": doctor["specialty"],
                    "date": datetime.strptime(slot_date, "%Y-%m-%d").date(),
                    "time": slot_time,
                    "location": doctor["location"],
                }
            )
    return flattened


def list_top_slot_options(doctor_availabilities: list[dict], limit: int = 3):
    slots = flatten_doctor_availabilities(doctor_availabilities)
    return sorted(slots, key=lambda item: (item["date"], item["time"]))[:limit]


def find_next_slot_from_doctor_availabilities(doctor_availabilities: list[dict]):
    candidates = flatten_doctor_availabilities(doctor_availabilities)
    if not candidates:
        raise ValueError("No doctor availability found for the requested specialty.")
    selected = sorted(candidates, key=lambda item: (item["date"], item["time"]))[0]
    scheduled_for = datetime.strptime(
        f"{selected['date']} {selected['time']}", "%Y-%m-%d %H:%M"
    )
    return {
        "appointment_id": f"APT-{uuid.uuid4().hex[:10].upper()}",
        "doctor_name": selected["doctor_name"],
        "specialty": selected["specialty"],
        "scheduled_for": scheduled_for,
        "location": selected["location"],
    }


def find_next_slot(body_part: str):
    return find_next_slot_from_doctor_availabilities(get_doctor_availabilities(body_part))


def list_specialty_slots(body_part: str):
    slots = flatten_doctor_availabilities(get_doctor_availabilities(body_part))
    return sorted(slots, key=lambda item: (item["date"], item["time"]))[:20]
