# Aditya AI Voice Enterprise

Deterministic voice + text appointment scheduling demo built from the supplied project brief. It uses FastAPI, SQLite, CSV business data, and browser-native speech APIs. No LLM or paid AI API is required.

## Start locally

```powershell
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload
```

Then open <http://127.0.0.1:8000/>. The interactive workspace is at `/app/app.html`.

## Included flows

- Landing page with persistent light/dark theme
- 50 businesses loaded from `data/businesses.csv`
- Business-specific services and availability
- Deterministic intent/entity extraction for booking, availability, rescheduling, cancellation, and help
- SQLite-backed appointment creation, cancellation, and rescheduling API
- Dashboard metrics, recent activity, slot availability, and text chat
- Browser speech recognition microphone control when supported

The server creates `appointments.db` on first run and seeds a small set of demo appointments.
