# Peckish

Peckish is a Django hackathon app for accessible teach-to-learn studying. Students teach a curious flamingo mascot, get gentle follow-up questions, and turn misconceptions into fossil cards for later review.

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file:

```env
DJANGO_SECRET_KEY=local-dev-secret
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,testserver,172.26.210.21
DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000,http://172.26.210.21:8000

GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash

PECKISH_WEB_IMAGES=1
GOOGLE_CUSTOM_SEARCH_API_KEY=
GOOGLE_CUSTOM_SEARCH_ENGINE_ID=

GOOGLE_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_REDIRECT_URI=http://172.26.210.21:8000/accounts/google/callback/
```

Authenticate to Gemini Enterprise / Vertex AI locally:

```powershell
gcloud auth application-default login
gcloud config set project your-gcp-project-id
```

Enable the Vertex AI API in your Google Cloud project. Peckish uses the unified `google-genai` SDK with `vertexai=True` and Application Default Credentials, which avoids the AI Studio free-tier daily request cap.

Optional modes:

- **Vertex express mode:** set `GOOGLE_GENAI_USE_VERTEXAI_EXPRESS=1` and `GEMINI_API_KEY`.
- **Legacy AI Studio key:** set `GOOGLE_GENAI_USE_VERTEXAI=0` and `GEMINI_API_KEY`.

Run the app:

```powershell
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Open `http://127.0.0.1:8000/` on this computer, or `http://172.26.210.21:8000/` from another device on the same network.

## Google Login Setup

Create a Google OAuth web client in Google Cloud Console.

Use these local development values:

- Authorized JavaScript origin: `http://127.0.0.1:8000`
- Authorized redirect URI: `http://127.0.0.1:8000/accounts/google/callback/`
- LAN JavaScript origin: `http://172.26.210.21:8000`
- LAN redirect URI: `http://172.26.210.21:8000/accounts/google/callback/`

If you use `localhost` instead of `127.0.0.1`, add matching Google Console entries and set `GOOGLE_REDIRECT_URI=http://localhost:8000/accounts/google/callback/`.

## Mind Map Images

Mind maps use Gemini to create image search prompts, then Peckish looks for real educational images.

By default, it tries Wikimedia Commons with no extra setup. For Google image results, configure a Programmable Search Engine that supports image search and add:

```env
GOOGLE_CUSTOM_SEARCH_API_KEY=your-custom-search-api-key
GOOGLE_CUSTOM_SEARCH_ENGINE_ID=your-programmable-search-engine-id
```

Google's Custom Search JSON API returns web and image search results from a Programmable Search Engine, but Google's docs say the JSON API is closed to new customers and existing customers transition by January 1, 2027. The Wikimedia fallback is there so the demo still works without those Google keys.

## Hackathon Notes

- Gemini calls are isolated behind `core/ai.py`, which uses `services/gemini_service.py` when Gemini Enterprise / Vertex AI (or a legacy AI Studio key) is configured.
- Without a key, Peckish uses local fallback logic so the demo flow still works.
- User accounts are required. Google OAuth signs users into Django, and study sessions are stored in SQLite against the logged-in user.
- First-time users choose an SEN learning profile: default, dyslexia, autism, ADHD, dyscalculia, or dyspraxia/DCD.
- Peckish adapts sessions using that profile and can convert notes into Gemini-backed flashcards, mind maps, or flow charts.
- Mind maps include Gemini-generated visual styling and image prompts for each node, plus cached web images from Google Custom Search or Wikimedia Commons where available.
- The app uses SQLite, Django templates, Tailwind CDN, vanilla JavaScript, browser speech recognition, MediaRecorder fallback transcription through Gemini, and browser text-to-speech.
