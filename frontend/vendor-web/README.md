# Vendor Directory (Next.js)

Frontend for listing, adding, viewing, and editing vendors against a Frappe backend.

## Local development

```bash
cp ../../.env.example .env.local
# set FRAPPE_URL, FRAPPE_API_KEY, FRAPPE_API_SECRET
npm install
npm run dev
```

Open http://localhost:3000

## Docker

Built from the repo root via `docker compose up --build frontend`.
