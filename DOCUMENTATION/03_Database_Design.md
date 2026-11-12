# Database Design

The application initializes its SQLite schema on startup. Primary/foreign keys and selected `CHECK` constraints enforce relational integrity and supported values.

```mermaid
erDiagram
  DEPARTMENTS ||--o{ USERS : staffs
  USERS ||--o{ AUTH_SESSIONS : authenticates
  USERS ||--o{ GRIEVANCES : submits
  DEPARTMENTS ||--o{ GRIEVANCES : assigned_to
  GRIEVANCES ||--o{ GRIEVANCE_HISTORY : records
  USERS ||--o{ GRIEVANCE_HISTORY : changes
  GRIEVANCES ||--o{ DEPARTMENT_ASSIGNMENTS : routes
  USERS ||--o{ DEPARTMENT_ASSIGNMENTS : assigns
  GRIEVANCES ||--o{ DEPARTMENT_REPORTS : receives
  USERS ||--o{ DEPARTMENT_REPORTS : authors
  GRIEVANCES ||--o{ ATTACHMENTS : includes
  USERS ||--o{ AI_SUGGESTIONS : requests
  GRIEVANCES o|--o{ AI_SUGGESTIONS : links
  GRIEVANCES ||--o| CITIZEN_FEEDBACK : rates
  USERS ||--o{ CITIZEN_FEEDBACK : provides
  GRIEVANCES ||--o{ GRIEVANCE_INTERNAL_REMARKS : has
  GRIEVANCES ||--o{ GRIEVANCE_ESCALATIONS : escalates
```

## Main entities

| Entity | Purpose |
|---|---|
| `users`, `auth_sessions` | Citizen/staff identities and hashed bearer-token sessions |
| `departments` | Seeded sample directory spanning health, education, food/civil supplies, social welfare, NORKA, infrastructure, transport, power/water, agriculture, industry/IT, and environment |
| `grievances` | Citizen complaint, current status, priority, and assignment |
| `grievance_history` | Append-only status transitions with actor, timestamp, and remark |
| `department_assignments` | Department/officer routing history |
| `department_reports` | Officer action report and CMO review decision |
| `attachments` | File metadata; file bytes live under `uploads/` |
| `ai_suggestions` | Advisory output, source/model, user, hashes, and optional grievance link |
| `citizen_feedback` | One 1–5 rating/comment per resolved grievance |
| `contact_enquiries` | Public questions and suggestions about the demonstration |
| `grievance_internal_remarks`, `grievance_escalations` | CMO-only notes and escalation records |

`citizen_feedback.grievance_id` is unique. Feedback is accepted only from the owning citizen and only once the case is resolved.
