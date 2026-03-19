import re
from datetime import datetime

from app.services.scheduling import BODY_PART_TO_SPECIALTY

REQUIRED_CHAT_FIELDS = (
    "full_name",
    "dob",
    "phone",
    "email",
    "body_part",
)

FIELD_LABELS = {
    "full_name": "full name",
    "dob": "date of birth",
    "phone": "phone number",
    "email": "email address",
    "body_part": "body area or specialty need",
}

FIELD_PROMPTS = {
    "full_name": "What is your full name?",
    "dob": "What is your date of birth?",
    "phone": "What phone number should we use for your appointment?",
    "email": "What email address should we send the confirmation to?",
    "body_part": "What body area or specialty do you want to schedule for?",
}


def update_intake_from_message(intake: dict, message: str) -> dict:
    updated = dict(intake)
    normalized_message = " ".join(message.strip().split())
    expected_field = updated.get("_next_field")

    if expected_field:
        direct_value = extract_direct_answer(expected_field, normalized_message)
        if direct_value:
            updated[expected_field] = direct_value
            if expected_field == "body_part":
                updated.setdefault("reason", f"Scheduling visit for {direct_value} concern.")

    email = extract_email(normalized_message)
    if email:
        updated["email"] = email

    phone = extract_phone(normalized_message)
    if phone:
        updated["phone"] = phone

    dob = extract_dob(normalized_message)
    if dob:
        updated["dob"] = dob

    full_name = extract_name(normalized_message)
    if full_name:
        updated["full_name"] = full_name

    body_part = extract_body_part(normalized_message)
    if body_part:
        updated["body_part"] = body_part
        updated.setdefault("reason", f"Scheduling visit for {body_part} concern.")

    if "sms_opt_in" not in updated:
        updated["sms_opt_in"] = False

    sms_opt_in = extract_sms_opt_in(normalized_message)
    if sms_opt_in is not None:
        updated["sms_opt_in"] = sms_opt_in

    if not updated.get("reason") and should_treat_as_reason(normalized_message):
        updated["reason"] = normalized_message[:300]

    updated.pop("_next_field", None)

    return updated


def missing_intake_fields(intake: dict) -> list[str]:
    return [field for field in REQUIRED_CHAT_FIELDS if not intake.get(field)]


def build_missing_fields_prompt(intake: dict, previous_intake: dict | None = None) -> str:
    missing = missing_intake_fields(intake)
    if not missing:
        intake.pop("_next_field", None)
        return "I have everything needed to schedule your appointment."

    next_field = missing[0]
    intake["_next_field"] = next_field

    if previous_intake is None:
        previous_intake = {}

    acknowledged_fields = [
        FIELD_LABELS[field]
        for field in REQUIRED_CHAT_FIELDS
        if intake.get(field) and not previous_intake.get(field)
    ]

    if acknowledged_fields:
        if len(acknowledged_fields) == 1:
            acknowledgement = f"Thanks, I have your {acknowledged_fields[0]}. "
        else:
            joined = ", ".join(acknowledged_fields[:-1])
            tail = acknowledged_fields[-1]
            acknowledgement = f"Thanks, I have your {joined} and {tail}. " if joined else f"Thanks, I have your {tail}. "
    else:
        acknowledgement = ""

    return f"{acknowledgement}{FIELD_PROMPTS[next_field]}"


def extract_direct_answer(expected_field: str, message: str) -> str | None:
    if expected_field == "full_name":
        return extract_name(message, allow_plain=True)
    if expected_field == "dob":
        return extract_dob(message)
    if expected_field == "phone":
        return extract_phone(message)
    if expected_field == "email":
        return extract_email(message)
    if expected_field == "body_part":
        return extract_body_part(message, allow_plain=True)
    return None


def extract_email(message: str) -> str | None:
    match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", message, re.IGNORECASE)
    return match.group(0) if match else None


def extract_phone(message: str) -> str | None:
    match = re.search(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", message)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return match.group(0).strip()


def extract_dob(message: str) -> str | None:
    patterns = [
        (r"\b\d{4}-\d{2}-\d{2}\b", ["%Y-%m-%d"]),
        (r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", ["%m/%d/%Y", "%m/%d/%y"]),
        (r"\b[A-Za-z]+\s+\d{1,2},\s*\d{4}\b", ["%B %d, %Y", "%b %d, %Y"]),
    ]
    for pattern, formats in patterns:
        match = re.search(pattern, message)
        if not match:
            continue
        for date_format in formats:
            try:
                return datetime.strptime(match.group(0), date_format).date().isoformat()
            except ValueError:
                continue
    return None


def extract_name(message: str, allow_plain: bool = False) -> str | None:
    patterns = [
        r"\bmy name is\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){1,2})\b",
        r"\bi am\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){1,2})\b",
        r"\bi'm\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){1,2})\b",
        r"\bthis is\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){1,2})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return " ".join(part.capitalize() for part in match.group(1).split())

    if allow_plain:
        plain_match = re.fullmatch(r"[A-Za-z]+(?:\s+[A-Za-z]+){1,2}", message.strip())
        if plain_match:
            return " ".join(part.capitalize() for part in plain_match.group(0).split())
    return None


def extract_body_part(message: str, allow_plain: bool = False) -> str | None:
    lowered = message.lower()
    for body_part in sorted(BODY_PART_TO_SPECIALTY, key=len, reverse=True):
        if body_part in lowered:
            return body_part
    if allow_plain and re.fullmatch(r"[A-Za-z][A-Za-z\s-]{1,60}", message.strip()):
        return message.strip().lower()
    return None


def extract_sms_opt_in(message: str) -> bool | None:
    lowered = message.lower()
    if "sms" not in lowered and "text" not in lowered:
        return None
    if any(token in lowered for token in ("yes", "opt in", "okay", "ok", "sure")):
        return True
    if any(token in lowered for token in ("no", "opt out", "don't", "do not")):
        return False
    return None


def should_treat_as_reason(message: str) -> bool:
    if len(message.split()) < 4:
        return False
    excluded_tokens = ("@", "dob", "date of birth", "phone", "call me", "my name is")
    return not any(token in message.lower() for token in excluded_tokens)