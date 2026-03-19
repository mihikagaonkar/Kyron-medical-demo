from openai import OpenAI
from app.config import settings

SYSTEM_GUARDRAILS = (
    "You are Kyron Medical's AI Patient Assistant for intake and scheduling. "
    "Never provide diagnosis, treatment plans, medication advice, or emergency instructions beyond: "
    "'If this is urgent, call emergency services now.' "
    "Keep responses short, empathetic, and operational. "
    "Focus on collecting missing intake details, proposing appointment next steps, "
    "or confirming handoff to phone support. Refuse harmful, illegal, hateful, or explicit requests."
)


class AIService:
    def __init__(self):
        self.client = (
            OpenAI(
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
            )
            if settings.groq_api_key
            else None
        )

    def generate(self, message: str, chat_history: list[dict], patient_context: dict) -> str:
        context_text = (
            f"Patient context: {patient_context}. "
            "You are a scheduling agent, not a clinical triage agent. "
            "Use the stored context only to book, confirm, reschedule, or hand off the appointment. "
            "Do not ask follow-up questions about symptoms, severity, diagnosis, or the ailment itself unless a required scheduling field is missing."
        )

        if self.client:
            messages = [
                {"role": "system", "content": SYSTEM_GUARDRAILS},
                {"role": "system", "content": context_text},
                *chat_history,
                {"role": "user", "content": message},
            ]
            response = self.client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                temperature=0.3,
            )
            return response.choices[0].message.content or "I can help you with scheduling next."

        fallback = (
            "I can help with intake and scheduling only. "
            "Please share your body area concern, preferred contact method, and I can arrange the next available visit."
        )
        return fallback
