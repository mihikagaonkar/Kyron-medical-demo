from datetime import date, datetime

import httpx
from app.config import settings
from app.services.chat_intake import FIELD_LABELS, missing_intake_fields


class VoiceService:
    @staticmethod
    def _json_safe(value):
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: VoiceService._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [VoiceService._json_safe(item) for item in value]
        return value

    @staticmethod
    def _short_text(value: str | None, fallback: str = "not provided", limit: int = 220) -> str:
        if not value:
            return fallback
        normalized = " ".join(str(value).split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 3]}..."

    @staticmethod
    def _optional_text(value: str | None, limit: int = 220) -> str | None:
        if not value:
            return None
        normalized = " ".join(str(value).split())
        if not normalized:
            return None
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 3]}..."

    @staticmethod
    def _is_valid_email(value: str | None) -> bool:
        return bool(value and "@" in value and "." in value.split("@")[-1])

    @staticmethod
    def _format_missing_fields(missing_fields: list[str]) -> str:
        if not missing_fields:
            return "none"
        readable = [FIELD_LABELS.get(field, field.replace("_", " ")) for field in missing_fields]
        if len(readable) == 1:
            return readable[0]
        if len(readable) == 2:
            return f"{readable[0]} and {readable[1]}"
        return f"{', '.join(readable[:-1])}, and {readable[-1]}"

    def _build_vapi_variables(self, phone_number: str, context_payload: dict) -> dict:
        intake = context_payload.get("intake", {})
        appointment = context_payload.get("appointment", {})
        chat_history = context_payload.get("chat_history", [])[-6:]
        doctor_availabilities = context_payload.get("doctor_availabilities", [])
        proposed_slots = context_payload.get("proposed_slots", [])
        missing_fields = missing_intake_fields(intake)

        chat_lines = []
        for item in chat_history:
            role = item.get("role", "assistant")
            speaker = "Patient" if role == "user" else "Assistant"
            content = self._short_text(item.get("content"), fallback="", limit=120)
            if content:
                chat_lines.append(f"{speaker}: {content}")

        recent_chat_summary = " | ".join(chat_lines) if chat_lines else "No prior chat transcript available."

        patient_name = self._short_text(intake.get("full_name"))
        body_part = self._short_text(intake.get("body_part"))
        visit_reason = self._short_text(intake.get("reason"))
        appointment_datetime = self._short_text(appointment.get("scheduled_for"))
        appointment_doctor = self._short_text(appointment.get("doctor_name"))
        appointment_specialty = self._short_text(appointment.get("specialty"))
        appointment_location = self._short_text(appointment.get("location"))
        missing_fields_text = self._format_missing_fields(missing_fields)
        handoff_stage = "booking-confirmed" if appointment else "intake-in-progress"
        doctor_availability_summary = self._build_doctor_availability_summary(doctor_availabilities)
        slot_options_summary = self._build_slot_options_summary(proposed_slots, doctor_availabilities)

        handoff_summary = (
            f"This is a web-to-phone scheduling handoff for {patient_name}. "
            f"Primary need: {body_part}. Reason: {visit_reason}. "
            f"Missing scheduling fields: {missing_fields_text}. "
            f"Appointment status: doctor {appointment_doctor}, specialty {appointment_specialty}, "
            f"time {appointment_datetime}, location {appointment_location}. "
            f"Doctor availabilities: {doctor_availability_summary}. "
            f"Immediate slot options: {slot_options_summary}. "
            f"Recent chat: {recent_chat_summary}"
        )

        return {
            "patientName": patient_name,
            "patientDob": self._short_text(intake.get("dob")),
            "patientPhone": self._short_text(intake.get("phone") or phone_number),
            "patientEmail": self._short_text(intake.get("email")),
            "bodyPart": body_part,
            "visitReason": visit_reason,
            "smsOptIn": "yes" if intake.get("sms_opt_in") else "no",
            "appointmentDoctor": appointment_doctor,
            "appointmentSpecialty": appointment_specialty,
            "appointmentDateTime": appointment_datetime,
            "appointmentLocation": appointment_location,
            "doctorAvailabilities": doctor_availability_summary,
            "slotOptions": slot_options_summary,
            "missingFields": missing_fields_text,
            "handoffStage": handoff_stage,
            "recentChatSummary": recent_chat_summary,
            "handoffSummary": self._short_text(handoff_summary, limit=900),
        }

    def _build_doctor_availability_summary(self, doctor_availabilities: list[dict]) -> str:
        if not doctor_availabilities:
            return "No matched doctor availability is currently loaded."

        summaries = []
        for doctor in doctor_availabilities[:3]:
            slots = doctor.get("slots", [])[:4]
            slot_text = ", ".join(slots) if slots else "no open slots listed"
            summaries.append(
                f"{doctor.get('doctor', 'Unknown doctor')} ({doctor.get('specialty', 'unknown specialty')}) at {doctor.get('location', 'unknown location')}: {slot_text}"
            )
        return " | ".join(summaries)

    def _build_slot_options_summary(self, proposed_slots: list[dict], doctor_availabilities: list[dict]) -> str:
        slot_lines = []

        for index, slot in enumerate(proposed_slots[:5], start=1):
            scheduled_for = slot.get("scheduled_for")
            scheduled_for_text = self._short_text(scheduled_for, fallback="time not provided")
            if hasattr(scheduled_for, "strftime"):
                scheduled_for_text = scheduled_for.strftime("%b %d, %Y at %I:%M %p")
            slot_lines.append(
                f"Option {index}: {scheduled_for_text} with {slot.get('doctor_name', 'Unknown doctor')} at {slot.get('location', 'unknown location')}"
            )

        if slot_lines:
            return " | ".join(slot_lines)

        fallback_lines = []
        for doctor in doctor_availabilities[:3]:
            for index, slot in enumerate(doctor.get("slots", [])[:3], start=1):
                fallback_lines.append(
                    f"{doctor.get('doctor', 'Unknown doctor')} option {index}: {slot} at {doctor.get('location', 'unknown location')}"
                )

        return " | ".join(fallback_lines) if fallback_lines else "No slot options have been prepared yet."

    def _build_vapi_metadata(self, context_payload: dict, variable_values: dict) -> dict:
        intake = context_payload.get("intake", {})
        appointment = context_payload.get("appointment", {})
        doctor_availabilities = self._json_safe(context_payload.get("doctor_availabilities", []))
        proposed_slots = self._json_safe(context_payload.get("proposed_slots", []))
        print("[Voice Handoff] Context payload:", context_payload)
        print("[Voice Handoff] Variable values:", variable_values)
        return {
            "handoffStage": variable_values["handoffStage"],
            "missingFields": variable_values["missingFields"],
            "patientPhone": variable_values["patientPhone"],
            "patientName": variable_values["patientName"],
            "bodyPart": variable_values["bodyPart"],
            "appointmentDoctor": variable_values["appointmentDoctor"],
            "appointmentDateTime": variable_values["appointmentDateTime"],
            "doctorAvailabilities": doctor_availabilities,
            "proposedSlots": proposed_slots[:5],
            "chatHistoryCount": len(context_payload.get("chat_history", [])),
            "smsOptIn": variable_values["smsOptIn"],
            "intakeCaptured": sorted(
                [key for key, value in intake.items() if value and not str(key).startswith("_")]
            ),
            "appointmentPresent": bool(appointment),
            "handoffSummary": variable_values["handoffSummary"],
        }

    async def start_call(self, phone_number: str, context_payload: dict):
        provider = settings.voice_provider
        if provider == "vapi":
            if not settings.vapi_api_key or not settings.vapi_assistant_id:
                return {
                    "call_status": "skipped",
                    "provider": "vapi",
                    "call_reference": None,
                    "detail": "Vapi credentials missing; configure .env to place live calls.",
                }

            variable_values = self._build_vapi_variables(phone_number, context_payload)
            metadata = self._build_vapi_metadata(context_payload, variable_values)
            customer = {"number": phone_number}

            patient_name = self._optional_text(context_payload.get("intake", {}).get("full_name"))
            if patient_name:
                customer["name"] = patient_name

            patient_email = self._optional_text(context_payload.get("intake", {}).get("email"))
            if self._is_valid_email(patient_email):
                customer["email"] = patient_email

            payload = {
                "assistantId": settings.vapi_assistant_id,
                "phoneNumberId": settings.vapi_phone_number_id,
                "customer": customer,
                "assistantOverrides": {
                    "variableValues": variable_values,
                },
                "metadata": metadata,
            }
            print("[Voice Handoff] Outbound Vapi payload:", payload)
            headers = {
                "Authorization": f"Bearer {settings.vapi_api_key}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post("https://api.vapi.ai/call/phone", json=payload, headers=headers)
                print("[Voice Handoff] Vapi status:", response.status_code)
                print("[Voice Handoff] Vapi response:", response.text)
                if response.is_error:
                    return {
                        "call_status": "failed",
                        "provider": "vapi",
                        "call_reference": None,
                        "detail": f"Vapi call failed ({response.status_code}): {response.text}",
                    }
                data = response.json()
            return {
                "call_status": "initiated",
                "provider": "vapi",
                "call_reference": data.get("id"),
                "detail": "Outbound call started with contextual handoff.",
            }


        return {
            "call_status": "skipped",
            "provider": provider,
            "call_reference": None,
            "detail": "Unsupported provider. Set VOICE_PROVIDER to vapi or retell.",
        }
