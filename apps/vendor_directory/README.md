# Vendor Directory (Frappe App)

Admin-side Frappe app for vendor master data, portal user registration, and KYC review.

## Roles

| Role | Access |
|------|--------|
| **System Manager** / **Vendor Manager** | Full admin on Desk |
| **Vendor Portal User** | Own vendor record only (via Vendor Portal) |

## Admin workflow (Frappe Desk)

1. Create a **Vendor**
2. Click **Create Portal User** — set login email + temporary password
3. Vendor signs in on Next.js portal, updates profile, uploads KYC docs, submits for review
4. On Vendor form use **KYC** actions: Under Review / Verified / Reject

## Portal APIs

- `vendor_directory.api.portal.get_my_vendor`
- `vendor_directory.api.portal.update_my_vendor`
- `vendor_directory.api.portal.upload_kyc_document`
- `vendor_directory.api.portal.submit_for_kyc_review`
- `vendor_directory.api.portal.create_portal_user`
- `vendor_directory.api.portal.set_kyc_status`
