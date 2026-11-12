# AI Integration

## Purpose and safeguards

The AI Grievance Assistant analyzes a citizen-provided subject and description to suggest a department, grievance category, Low/Medium/High priority, a short CMO summary, and a possible duplicate flag. Suggestions are advisory only. Citizens can review suggestions before submission, and CMO administrators can inspect the saved suggestion alongside the grievance. The model never assigns a case, sets the official priority, changes status, or resolves a grievance.

Duplicate detection uses a local text-similarity heuristic against up to 500 recent unresolved grievances. It returns only a generic flag; it does not expose another citizen's reference number or complaint.

## Model/API configuration

The application supports an OpenAI-compatible chat-completions API:

- `AI_API_KEY`: provider credential; keep it in a local `.env` or deployment secret store.
- `AI_BASE_URL`: chat-completions endpoint. Defaults to `https://api.openai.com/v1/chat/completions`.
- `AI_MODEL`: model name. Defaults to `gpt-4o-mini`.

The prompt asks for JSON containing `suggested_department`, `category`, `priority`, `summary`, and `duplicate_possible`. The application validates department and category against current application options, restricts priority to Low/Medium/High, bounds summary length, and validates the duplicate flag as a boolean. Complaint text is treated as untrusted data in the prompt.

When configured, the application requires the citizen's explicit consent before sending the subject and description to the provider. The form explains this transfer. Do not send real citizen data to a third party without appropriate approval.

## Fallback and limitations

When `AI_API_KEY` is not configured, the endpoint uses a labelled local rule-based fallback to keep local testing possible. Its response explicitly states that it is not completed AI integration. If a configured provider fails or returns invalid data, the API reports an error instead of silently presenting fallback output as AI.

The fallback rules are illustrative, not a trained model. Duplicate detection is heuristic and can produce false positives or miss duplicates. Human review remains mandatory.

## Endpoints and persistence

- `GET /api/ai/status`: authenticated citizen check for provider configuration and data-handling notices.
- `POST /api/ai/analyze`: authenticated citizen request with subject, description, and external-AI consent.
- `ai_suggestions`: persists suggestion, source/model, user, and text hashes. On grievance submission, the suggestion is linked only if it belongs to that citizen and matches the submitted subject/description. The citizen tracking response and CMO case detail expose the linked suggestion.

## Local test

Copy `.env.example` to `.env`, configure a compatible API key/model endpoint, restart the application, sign in as a citizen, and use **Analyze complaint** on the grievance form. Without a configured key, verify the displayed fallback notice and do not claim that actual AI integration was exercised.
