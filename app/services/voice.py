import httpx
from app.config import settings


class VoiceService:
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

            payload = {
                "assistantId": settings.vapi_assistant_id,
                "phoneNumberId": settings.vapi_phone_number_id,
                "customer": {"number": phone_number},
                "metadata": {"chatContext": context_payload},
            }
            headers = {
                "Authorization": f"Bearer {settings.vapi_api_key}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post("https://api.vapi.ai/call", json=payload, headers=headers)
                response.raise_for_status()
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
