# Setup and Testing

## Local setup (Windows PowerShell)

```powershell
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`; API docs are at `/docs`. The database is initialized automatically. Use `python -m app.create_staff_account` to create local-only CMO/officer test accounts. Do not put credentials in the repository.

## Tests

Install development dependencies and run:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

Tests use a temporary SQLite database and synthetic data. They should not access the default `grievances.db` or call an external AI provider.

The committed automated tests currently cover public-page rendering, department listing, enquiry persistence, and citizen feedback ownership/eligibility. Validate the full citizen→CMO→officer→CMO lifecycle and configured external AI provider with the evaluation/demo checklist before making a completion claim.

## 3–5 minute demo recording checklist

1. **0:00–0:30:** Clarify that this is an independent demonstration and not an official government service; show the public pages and workflow explanation.
2. **0:30–1:20:** Register/sign in as a citizen, submit a fictional grievance, and note the generated reference.
3. **1:20–2:30:** Sign in as CMO, move it to Under Review, assign it to the correct department/officer, and show recorded history.
4. **2:30–3:30:** Sign in as that officer, add progress and submit an action-taken report.
5. **3:30–4:20:** Return as CMO, accept the report, and show the citizen-facing resolution and feedback form.
6. **4:20–5:00:** Show API docs and AI safeguards. Only claim actual AI if a live provider request was made with permitted demo text and consent; otherwise state that the fallback is labelled and live AI is not configured.

Use temporary test accounts and fictional data. Do not show credentials, API keys, or real personal information in the recording.

## AI configuration

See [AI Integration](./05_AI_Integration.md). A real provider key and permitted model/account are required to verify actual AI integration. Keep secrets in a local `.env` or the deployment secret manager; never paste them into source or chat.

## Container

```powershell
docker build -t cm-kerala-grievance .
docker run --rm -p 8000:8000 -v grievance-data:/data -e DATABASE_PATH=/data/grievances.db cm-kerala-grievance
```

Configure persistent storage for uploads as well as SQLite before deployment. This container build is not evidence that the application has been deployed to a public host.
