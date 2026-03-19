from datetime import date, datetime, timedelta
import itertools
import uuid

DOCTORS = [
    {
        "name": "Dr. Maya Patel",
        "specialty": "Orthopedics",
        "location": "Kyron Medical - Downtown"
    },
    {
        "name": "Dr. Ethan Brooks",
        "specialty": "Cardiology",
        "location": "Kyron Medical - West Campus"
    },
    {
        "name": "Dr. Leila Hassan",
        "specialty": "Neurology",
        "location": "Kyron Medical - Downtown"
    },
    {
        "name": "Dr. Jonah Reeves",
        "specialty": "Pulmonology",
        "location": "Kyron Medical - North Campus"
    },
    {
        "name": "Dr. Sofia Nguyen",
        "specialty": "Dermatology",
        "location": "Kyron Medical - East Campus"
    }
]

BODY_PART_TO_SPECIALTY = {
    "knee": "Orthopedics",
    "hip": "Orthopedics",
    "shoulder": "Orthopedics",
    "elbow": "Orthopedics",
    "ankle": "Orthopedics",
    "chest": "Cardiology",
    "heart": "Cardiology",
    "blood pressure": "Cardiology",
    "head": "Neurology",
    "brain": "Neurology",
    "migraine": "Neurology",
    "lung": "Pulmonology",
    "breathing": "Pulmonology",
    "cough": "Pulmonology",
    "skin": "Dermatology",
    "rash": "Dermatology",
    "acne": "Dermatology",
}

TIME_SLOTS = ["09:00", "10:30", "13:00", "15:30"]


def infer_specialty(body_part: str) -> str:
    lowered = body_part.strip().lower()
    for key, specialty in BODY_PART_TO_SPECIALTY.items():
        if key in lowered:
            return specialty
    return "Orthopedics"


def build_availability_window(days_ahead: int = 45):
    today = date.today()
    days = [today + timedelta(days=offset) for offset in range(1, days_ahead + 1)]
    weekdays = [d for d in days if d.weekday() < 5]

    availability = []
    cycle = itertools.cycle(TIME_SLOTS)
    for doctor in DOCTORS:
        for day in weekdays:
            if (day.day + len(doctor["name"])) % 2 == 0:
                availability.append(
                    {
                        "doctor_name": doctor["name"],
                        "specialty": doctor["specialty"],
                        "date": day,
                        "time": next(cycle),
                        "location": doctor["location"],
                    }
                )
    return availability


AVAILABILITY = build_availability_window()


def find_next_slot(body_part: str):
    specialty = infer_specialty(body_part)
    candidates = [slot for slot in AVAILABILITY if slot["specialty"] == specialty]
    if not candidates:
        candidates = AVAILABILITY
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


def list_specialty_slots(body_part: str):
    specialty = infer_specialty(body_part)
    slots = [slot for slot in AVAILABILITY if slot["specialty"] == specialty]
    return sorted(slots[:20], key=lambda item: (item["date"], item["time"]))
