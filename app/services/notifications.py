import smtplib
from email.mime.text import MIMEText
from twilio.rest import Client
from app.config import settings


class NotificationService:
    def send_email_confirmation(self, recipient: str, body: str) -> str:
        if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
            return "Email skipped (SMTP not configured)."

        msg = MIMEText(body)
        msg["Subject"] = "Kyron Medical Appointment Confirmation"
        msg["From"] = settings.smtp_from
        msg["To"] = recipient

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
        return "Email confirmation sent."

    def send_sms_confirmation(self, to_phone: str, body: str, opted_in: bool) -> str:
        if not opted_in:
            return "SMS skipped (patient did not opt in)."
        if (
            not settings.twilio_account_sid
            or not settings.twilio_auth_token
            or not settings.twilio_sms_from
        ):
            return "SMS skipped (Twilio not configured)."

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.messages.create(to=to_phone, from_=settings.twilio_sms_from, body=body)
        return "SMS confirmation sent."
