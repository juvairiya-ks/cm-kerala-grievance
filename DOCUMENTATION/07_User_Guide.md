# User Guide

This guide covers the local demonstration. It is not an official Government of Kerala service; do not enter real personal data.

## Citizen

1. Register at `/register` and sign in at `/login`.
2. Choose **Submit a grievance**, select a district/category, and provide the subject and details.
3. Optionally request AI suggestions. Review the notice; if an external provider is configured, explicitly consent before sending text. Suggestions are advisory and do not make decisions.
4. Submit and save the generated reference number. Track updates from the dashboard or `/citizen/track`.
5. When a grievance is resolved, submit a one-time rating and optional comment from its tracking page.

## CMO administrator

Staff accounts are created by the local project operator with `python -m app.create_staff_account`; there is no public staff registration. Sign in through the shared `/login` page. Review a submitted grievance, move it to **Under Review**, assign it to a department/officer, inspect reports, then accept the report to resolve or return/reopen it for more work.

## Department officer

The operator creates the officer account and assigns a department. Sign in through `/login`, open the officer dashboard, review assigned complaints, record progress, and submit an action-taken report. The CMO makes the final resolution decision.

## Contact and service limitations

The `/contact` form stores an enquiry in the local database; it does not send email or guarantee a response. This project is not an official government grievance service.
