# Kyron Medical Demo — AI Patient Assistant MVP

A web-based AI Patient Assistant for intake, semantic scheduling, and chat-to-voice handoff.

## Product Overview 
- Capture intake in one pass, assign the right specialist automatically, and confirm appointments instantly.
- Preserve context when escalating from web chat to voice assistant so patients never repeat themselves.


## Functional Coverage in this MVP
- **Patient Intake**: Name, DOB, Phone, Email, Reason, Body Part, SMS opt-in.
- **Semantic Scheduling**: Body-part mapping (e.g., `Knee -> Orthopedics`) to hard-coded doctors.
- **Availability Data**: Generated 45-day doctor schedule window on weekdays.
- **Context-Aware Handoff**: `Switch to Phone` endpoint launches outbound call via Vapi/Retell and includes chat + intake context.
- **Post-Booking Notifications**:
  - Email confirmation via SMTP.
  
- **Safety Guardrails**:
  - AI system prompt blocks diagnosis/treatment advice.
  - Restricts assistant to operational intake/scheduling content.

## Tech Stack
- **Backend**: FastAPI (Python)
- **Frontend**: HTML5 + Tailwind CSS + Vanilla JavaScript
- **AI/Voice**:
  - Groq for web chat
  - Vapi for voice handoff
  




## Technical Architecture (Brief)
1. Browser sends intake payload to FastAPI `/api/intake_schedule`.
2. Backend applies semantic mapping and picks nearest specialty-matched slot from in-memory availability.
3. Backend sends email confirmation through SMTP.
4. Chat requests hit `/api/chat`,  with strict guardrail prompt.
5. Voice handoff calls `/api/switch-to-phone`, which forwards session context to Vapi outbound call API.
6. Frontend receives status updates and displays booking/handoff outcomes in real time.



## Run Locally
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set required API keys.
4. Start app:
   ```bash
   uvicorn app.main:app --reload
   ```
5. Open `http://localhost:8000`.

## Project Structure
- `app/main.py` — API routes + frontend static serving
- `app/models.py` — Pydantic request/response models
- `app/config.py` — environment-based settings
- `app/services/ai.py` — AI chat with guardrails
- `app/services/scheduling.py` — semantic routing + availability logic
- `app/services/voice.py` — Vapi outbound call bridge
- `app/services/notifications.py` — SMTP 
- `app/static/index.html` — glassmorphism UI shell
- `app/static/app.js` — client-side workflow logic
