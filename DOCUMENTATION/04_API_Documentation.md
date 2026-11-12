# API Documentation

Interactive OpenAPI documentation is available at `/docs`; the schema is at `/openapi.json`. Unless noted otherwise, protected routes require `Authorization: Bearer <access_token>`. Public citizen registration cannot create staff accounts.

## Public and authentication

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health probe |
| GET | `/api/departments` | Department directory |
| POST | `/api/contact` | Store an enquiry (`name`, `email`, `subject`, `message`) |
| POST | `/api/auth/register` | Create citizen account |
| POST | `/api/auth/login` | Sign in and receive 24-hour bearer token |
| GET | `/api/auth/me` | Read current account |
| POST | `/api/auth/logout` | Revoke current session |

## Citizen and AI

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/grievances/options` | District/category choices |
| POST | `/api/grievances` | Submit multipart grievance and optional attachment |
| GET | `/api/grievances` | List current citizen's grievances |
| GET | `/api/grievances/{reference_number}` | Details, status history, attachment metadata, and linked AI advice |
| GET | `/api/grievances/{reference_number}/attachments/{attachment_id}` | Authorized attachment download |
| POST | `/api/grievances/{reference_number}/feedback` | Submit one rating/comment after resolution |
| GET | `/api/ai/status` | Provider configuration and consent notice |
| POST | `/api/ai/analyze` | Analyze complaint; external provider requires explicit consent |

## CMO and department officer

Admin paths use `/api/admin`; officer paths use `/api/officer`.

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/api/admin/stats` | Admin | Totals and district/department counts |
| GET | `/api/admin/departments` | Admin | Departments and officers for assignment |
| GET | `/api/admin/grievances` | Admin | Filtered grievance list |
| GET | `/api/admin/grievances/{id}` | Admin | Full case, history, reports, remarks, AI advice |
| POST | `/api/admin/grievances/{id}/review` | Admin | Move Submitted to Under Review |
| POST | `/api/admin/grievances/{id}/assign` | Admin | Route to department/officer; advance to In Progress |
| POST | `/api/admin/grievances/{id}/remarks` | Admin | Add internal remark |
| POST | `/api/admin/grievances/{id}/escalate` | Admin | Escalate unresolved case |
| POST | `/api/admin/grievances/{id}/reopen` | Admin | Reopen resolved case |
| POST | `/api/admin/reports/{id}/review` | Admin | Accept or return action report |
| GET | `/api/admin/grievances/{id}/attachments/{attachment_id}` | Admin | Authorized file download |
| GET | `/api/officer/grievances` | Officer | List current department assignments |
| GET | `/api/officer/grievances/{id}` | Officer | Assigned case details |
| POST | `/api/officer/grievances/{id}/update` | Officer | Record investigation progress |
| POST | `/api/officer/grievances/{id}/reports` | Officer | Submit action report and resolution details |
| GET | `/api/officer/grievances/{id}/attachments/{attachment_id}` | Officer | Authorized file download |

Request schemas and response models are discoverable from `/docs`. See [README](../README.md) for running the server and creating staff accounts.
