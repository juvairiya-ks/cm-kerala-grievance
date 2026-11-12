# Project Overview

## Purpose

The CM Kerala Grievance Portal is an independent demonstration of a public-service grievance workflow. It is not an official Government of Kerala service. Use fictional information only.

## Roles and capabilities

- **Citizen:** creates an account, submits a grievance, optionally attaches a PDF/image, views lifecycle history, reviews optional AI advice, and leaves feedback after resolution.
- **CMO administrator:** reviews submitted grievances, assigns them to departments/officers, records private remarks, reviews action reports, resolves or reopens cases, and monitors summary statistics.
- **Department officer:** views assigned grievances, records investigation updates, and submits an action-taken report for CMO review.
- **Public visitor:** reads service information, workflow, sample departments, FAQs, and sends an enquiry.

## Status lifecycle

`Submitted → Under Review → In Progress → Resolved`

The CMO may reopen a resolved grievance (`Reopened`) and forward it again. Each status transition is recorded with its timestamp, actor, previous status, and remark. The officer's report alone does not resolve a grievance; the CMO reviews it.

## Technology

- Python 3.13 (tested locally), FastAPI, Uvicorn, Pydantic
- Server-rendered HTML/Jinja2, CSS, browser JavaScript
- SQLite, with a configurable database path
- Optional OpenAI-compatible AI chat-completions provider

## Limitations

Email/SMS delivery, production-grade identity proofing, official hosting, and a live external AI provider are not verified. Read [AI Integration](./05_AI_Integration.md) before enabling external analysis. This demonstration is not operated by the Government of Kerala.
