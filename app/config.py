import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    app_env = os.getenv("APP_ENV")
    app_host = os.getenv("APP_HOST")
    app_port = int(os.getenv("APP_PORT", 8000))

    groq_api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL")

    voice_provider = os.getenv("VOICE_PROVIDER").lower()
    vapi_api_key = os.getenv("VAPI_API_KEY")
    vapi_assistant_id = os.getenv("VAPI_ASSISTANT_ID")
    vapi_phone_number_id = os.getenv("VAPI_PHONE_ID")

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM")

    public_base_url = os.getenv("PUBLIC_BASE_URL")


settings = Settings()
