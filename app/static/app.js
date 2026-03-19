const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const chatLog = document.getElementById('chatLog');
const smsOptInToggle = document.getElementById('smsOptInToggle');
const switchToPhoneBtn = document.getElementById('switchToPhoneBtn');
const handoffStatus = document.getElementById('handoffStatus');

let sessionId = localStorage.getItem('kyron_session_id') || '';
let smsOptIn = localStorage.getItem('kyron_sms_opt_in') === 'true';
let doctorAvailabilities = JSON.parse(localStorage.getItem('kyron_doctor_availabilities') || '[]');
let proposedSlots = JSON.parse(localStorage.getItem('kyron_proposed_slots') || '[]');

smsOptInToggle.checked = smsOptIn;

smsOptInToggle.addEventListener('change', () => {
  smsOptIn = smsOptInToggle.checked;
  localStorage.setItem('kyron_sms_opt_in', String(smsOptIn));
});

function addChatMessage(role, text) {
  const msg = document.createElement('div');
  msg.className = `rounded-xl p-3 text-sm ${role === 'user' ? 'bg-blue/40 ml-8' : 'bg-white/15 mr-8'}`;
  msg.textContent = text;
  chatLog.appendChild(msg);
  chatLog.scrollTop = chatLog.scrollHeight;
}

if (!chatLog.hasChildNodes()) {
  addChatMessage('assistant', 'I can help schedule appointments, check availability, reschedule visits, or arrange a phone callback.');
}

chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  if (!sessionId) {
    sessionId = `web-${Date.now()}`;
    localStorage.setItem('kyron_session_id', sessionId);
  }

  addChatMessage('user', message);
  chatInput.value = '';

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message, sms_opt_in: smsOptIn })
    });
    if (!response.ok) {
      throw new Error('Chat service unavailable.');
    }
    const data = await response.json();
    if (data.phone) {
      localStorage.setItem('kyron_phone', data.phone);
    }
    doctorAvailabilities = data.doctor_availabilities || [];
    proposedSlots = data.proposed_slots || [];
    localStorage.setItem('kyron_doctor_availabilities', JSON.stringify(doctorAvailabilities));
    localStorage.setItem('kyron_proposed_slots', JSON.stringify(proposedSlots));
    addChatMessage('assistant', data.response);
  } catch (error) {
    addChatMessage('assistant', error.message);
  }
});

switchToPhoneBtn.addEventListener('click', async () => {
  let phone = localStorage.getItem('kyron_phone') || '';

  if (!phone) {
    phone = window.prompt('Enter the phone number you want us to call:', '')?.trim() || '';
    if (phone) {
      localStorage.setItem('kyron_phone', phone);
    }
  }

  if (!sessionId && !phone) {
    handoffStatus.textContent = 'Enter a callback number to start the phone handoff.';
    return;
  }

  handoffStatus.textContent = 'Connecting phone handoff...';
  try {
    const response = await fetch('/api/switch-to-phone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId || phone,
        phone,
        doctor_availabilities: doctorAvailabilities,
        proposed_slots: proposedSlots
      })
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Handoff failed.');
    }

    handoffStatus.textContent = `${data.detail} Provider: ${data.provider}. Ref: ${data.call_reference || 'N/A'}`;
  } catch (error) {
    handoffStatus.textContent = error.message;
  }
});
