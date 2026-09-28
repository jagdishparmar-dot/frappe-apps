# hrms_custom

Standalone HRMS app for the Frappe Framework, implementing `HRMS_Technical_Spec.md`.
How to run the site in development and production: [`../../README.md`](../../README.md).
It depends on Frappe only: ERPNext and Frappe HR are **not** required and **cannot** be installed on
the same site, because this app defines its own `Employee`, `Company`, `Department`, `Designation`,
`Branch` and `Employee Checkin` doctypes.

On the desk it appears as the **HRMS** app icon, which opens the HRMS workspace (`/desk/hrms`).

## Endpoints

All custom endpoints return the envelope `{"success": bool, "message": str, "data": {...}}`
at the top level of the JSON body, with a matching HTTP status code.

| Method | Path | Auth |
|---|---|---|
| POST | `/api/method/hrms_custom.api.auth.request_otp` | guest |
| POST | `/api/method/hrms_custom.api.auth.verify_otp` | guest |
| POST | `/api/method/hrms_custom.api.auth.logout` | token |
| GET | `/api/method/hrms_custom.api.profile.get_my_profile` | token |
| POST | `/api/method/hrms_custom.api.profile.request_profile_update` | token (Active employee): JSON `changes` |
| POST | `/api/method/hrms_custom.api.profile.cancel_profile_update` | token (own Pending request) |
| POST | `/api/method/hrms_custom.api.profile.review_profile_update` | HR: `request`, `status` (Approved/Rejected), `remarks` |
| GET | `/api/method/hrms_custom.api.profile.list_profile_updates?employee=&status=` | token (own), HR (any) |
| GET | `/api/method/hrms_custom.api.attendance.get_punch_status` | token |
| POST | `/api/method/hrms_custom.api.attendance.punch` | token |
| GET/POST | `/api/method/hrms_custom.api.attendance.my_attendance?month=` | token (Active); `YYYY-MM` of daily status, times and worked hours |
| GET/POST | `/api/method/hrms_custom.api.attendance.get_live_attendance?date=&company=&department=` | HR; one-day present/absent/late/on-leave (defaults to today). POST is required for the Desk page (`frappe.call`). |
| GET | `/api/method/hrms_custom.api.regularization.my_regularizations?status=` | token (Active) |
| POST | `/api/method/hrms_custom.api.regularization.request_regularization` | token (Active); `date`, `reason`, optional IN/OUT times |
| POST | `/api/method/hrms_custom.api.regularization.cancel_regularization` | token; own Open request |
| POST | `/api/method/hrms_custom.api.regularization.review_regularization` | HR: `request`, `status` (Approved/Rejected), `remarks` |
| POST | `/api/method/hrms_custom.api.regularization.approve_regularization` | HR alias for Approved |
| GET | `/api/method/hrms_custom.api.regularization.list_regularizations?employee=&status=` | token (own), HR (any) |
| POST | `/api/method/hrms_custom.api.onboarding.invite_employee` | HR (desk session) |
| GET | `/api/method/hrms_custom.api.onboarding.get_onboarding_form` | token (invited joiner) |
| POST | `/api/method/hrms_custom.api.onboarding.upload_onboarding_document` | token, multipart `file` + `document_type` |
| POST | `/api/method/hrms_custom.api.onboarding.delete_onboarding_document` | token |
| POST | `/api/method/hrms_custom.api.onboarding.submit_onboarding_form` | token |
| GET | `/api/method/hrms_custom.api.documents.list_documents?employee=` | token (own), HR (any employee) |
| POST | `/api/method/hrms_custom.api.documents.upload_document` | token, multipart `file` + `document_type` (+ `replaces`) |
| POST | `/api/method/hrms_custom.api.documents.delete_document` | token (own, Pending only) |
| POST | `/api/method/hrms_custom.api.documents.verify_document` | HR: `document`, `status` (Verified/Rejected), `remarks` |
| GET | `/api/method/hrms_custom.api.documents.download_document?document=` | owner or HR; returns the file bytes |
| GET | `/api/method/hrms_custom.api.shift.list_shift_types` | token; HR may pass `include_inactive=1` |
| POST | `/api/method/hrms_custom.api.shift.create_shift_type` | HR |
| GET | `/api/method/hrms_custom.api.shift.my_shift_calendar?month=` | token (Active); `month` is `YYYY-MM` |
| GET | `/api/method/hrms_custom.api.shift.get_roster?department=&month=&company=` | HR; employees × days for `YYYY-MM` |
| POST | `/api/method/hrms_custom.api.shift.bulk_assign_roster` | HR; JSON `entries` of `{employee, date, shift_type}` (empty type clears) |
| GET | `/api/method/hrms_custom.api.leave.my_leave_balance?year=` | token (Active); year defaults to current |
| GET | `/api/method/hrms_custom.api.leave.my_leave_applications?status=` | token (Active) |
| GET | `/api/method/hrms_custom.api.leave.preview_leave` | token; `leave_type`, `from_date`, `to_date`, optional `half_day` |
| POST | `/api/method/hrms_custom.api.leave.apply_leave` | token (Active) |
| POST | `/api/method/hrms_custom.api.leave.cancel_leave` | token; own Open application |
| POST | `/api/method/hrms_custom.api.leave.review_leave` | HR: `application`, `status` (Approved/Rejected), `remarks` |
| GET | `/api/method/hrms_custom.api.leave.list_leave_applications?employee=&status=` | token (own), HR (any) |

Desk **Script Reports** (HR roles, export from the report view): Attendance Summary, Employee
Date-wise Attendance (background / prepared, one row per employee per day with IN/OUT and
status), Punch Log, Late Coming / Early Going, Leave Balance, Employee Master, Onboarding Status.

Desk page **Live Attendance** (`/desk/live-attendance`) shows the same one-day counts plus an
employee table and reloads every 60 seconds.

Mobile clients send `Authorization: token <api_key>:<api_secret>`.

### Self-onboarding flow

1. HR creates an `Employee` with status **Inactive** and just the name, joining date, mobile and
   email, then clicks **Invite to Onboard**. This creates the User and sets
   `onboarding_status = Invited`.
2. The joiner signs in to the mobile app with an OTP. Until they are verified, the app only shows
   the onboarding form, and punching is refused.
3. The joiner submits the form: personal, contact, bank and emergency details, plus documents (at
   least one ID proof). `onboarding_status` becomes **Pending Verification**, an
   `Onboarding Checklist` is created and users with HR Admin or HR Executive are emailed.
4. HR reviews the record and clicks **Mark Verified & Activate**.

Emails are best-effort. On a site with no outgoing Email Account the invite still succeeds, and
the desk shows a warning.

## Tests

```bash
bash /workspace/scripts/run-tests.sh   # uses a dedicated test.localhost site
```
