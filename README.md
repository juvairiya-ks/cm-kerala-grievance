# CM Kerala Grievance Portal

An independent demonstration of a public grievance-service workflow. This application is not an official Government of Kerala service. Use fictional demonstration data only.

## Stack

- HTML and CSS templates
- Python with FastAPI
- SQLite for persistent application data

## Run locally

From the project root in PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` for the landing page and `http://127.0.0.1:8000/docs` for the API documentation. The health endpoint is `http://127.0.0.1:8000/health`.

The database and sample departments are created automatically when the app starts. List departments at `http://127.0.0.1:8000/api/departments`.

## Authentication API

- `POST /api/auth/register` creates a citizen account. Public registration cannot create administrator or officer accounts.
- `POST /api/auth/login` verifies credentials and returns a 24-hour bearer token.
- `GET /api/auth/me` returns the signed-in user's profile. Send `Authorization: Bearer <access_token>`.
- `POST /api/auth/logout` revokes the current bearer token.

Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes. The database stores only a hash of each session token. Do not use real personal data in this demonstration.

## Citizen pages

- `/register` creates a citizen account through the registration API.
- `/login` signs in and stores the bearer token for the current browser tab session.
- `/citizen/dashboard` shows the signed-in citizen's grievances and counts.
- `/citizen/grievances/new` submits a grievance with an optional PDF, PNG, JPG, or JPEG attachment (5 MB maximum).
- `/citizen/track` shows the status history for a reference number belonging to the signed-in citizen.

Grievance endpoints require `Authorization: Bearer <access_token>`:

- `GET /api/grievances/options` lists supported districts and categories.
- `POST /api/grievances` accepts multipart form fields `district`, `category`, `subject`, `description`, and optional `attachment`.
- `GET /api/grievances` lists the signed-in citizen's grievances and dashboard counts.
- `GET /api/grievances/{reference_number}` returns details and status history, scoped to the signed-in citizen.
- `GET /api/grievances/{reference_number}/attachments/{attachment_id}` downloads an attachment after checking ownership.

Uploads are stored under `uploads/`, which is ignored by Git. This local-file storage is intended for demonstration; a production deployment should use persistent/object storage.

## CMO and department officer workflow

Create a staff account from the project root using `python -m app.create_staff_account`. This local command interactively creates an administrator or department officer and does not expose staff registration publicly. For officer accounts, select one of the seeded department IDs shown by the command.

- `/admin/dashboard` is the CMO workspace.
- `/officer/dashboard` is the department officer workspace.
- Successful login redirects to the dashboard for the account's role.
- CMO review and department forwarding are separate actions: mark a submitted case `Under Review`, then assign it to move it to `In Progress`.
- CMO API routes under `/api/admin` provide counts, district/department statistics, grievance filters and details, internal remarks, assignment, attachment retrieval, and action-report review.
- Officer API routes under `/api/officer` list only their latest department assignments, record progress, and submit action-taken/resolution reports.
- Accepting an action report resolves the grievance; returning a report keeps it in progress for more work. Internal CMO remarks are kept separate from citizen-visible status history.
- The CMO can reopen a resolved grievance and escalate unresolved cases older than 14 days. Approved resolution details are shown to citizens only while the grievance is resolved.

Staff logins use the same sign-in page as citizens. Do not use real government credentials or real citizen information.

## AI Grievance Assistant

The citizen grievance form can request advisory suggestions for department, category, priority, a short CMO summary, and a possible duplicate. The citizen can inspect the suggestion and explicitly apply the suggested category. A generated suggestion is linked to the submitted grievance and is visible to that citizen and to CMO reviewers. It never sets the official grievance priority, assigns a department, changes status, or resolves a case.

### Configure an actual AI model

1. Copy `.env.example` to `.env`.
2. Set `AI_API_KEY` to a key for an OpenAI-compatible chat-completions provider. Keep the key local and never commit `.env`.
3. Set `AI_BASE_URL` to that provider's chat-completions URL and `AI_MODEL` to a model available to your account.
4. Restart the server. With a provider configured, the citizen must explicitly consent before their subject and description are sent to it.

The default provider URL/model target OpenAI's compatible API shape; compatible providers can be configured with the two environment settings. The assistant validates model output against the database's department/category lists and only allows Low/Medium/High priorities. Provider or invalid-output failures are reported; they do not silently downgrade an attempted AI request to a fallback.

### Without a provider key

The endpoint returns a clearly labelled local rule-based fallback when no provider is configured. This fallback is **not completed AI integration** and must not be presented as such in the submission. Duplicate checking is a local similarity heuristic and is only a human-review flag. Do not use real citizen data; with an external provider configured, complaint subject/description leave the app for analysis.

API:

- `GET /api/ai/status` reports whether a provider is configured and explains data handling.
- `POST /api/ai/analyze` accepts `{ "subject": "...", "description": "...", "consent_to_external_ai": true }` with citizen bearer authentication.
- Analysis responses include `source`, `model`, `notice`, and `requires_human_review`; `suggestion_id` is attached to the grievance when that same citizen submits matching subject/description.

## Public information pages and feedback

- `/about`, `/how-it-works`, `/departments`, and `/faq` provide public project information.
- `/contact` stores enquiries locally through `POST /api/contact`; it does not send email or guarantee a response.
- Citizens may submit one 1–5 rating/comment after their grievance is resolved using `POST /api/grievances/{reference_number}/feedback`.

## Documentation and tests

The [documentation set](DOCUMENTATION/01_Project_Overview.md) includes an overview, architecture and ER diagrams, API reference, AI safeguards, setup/testing, and role-based user guide.

Run the automated checks after installing development dependencies:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Container

Build and run locally:

```powershell
docker build -t cm-kerala-grievance .
docker run --rm -p 8000:8000 `
  -v grievance-data:/data `
  -v grievance-uploads:/app/uploads `
  -e DATABASE_PATH=/data/grievances.db `
  cm-kerala-grievance
```

This Dockerfile is a deployment starting point, not evidence that a public hosted deployment exists. Persist both volumes and configure secrets only in the hosting provider's secret manager.
