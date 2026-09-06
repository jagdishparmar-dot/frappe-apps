#!/bin/sh
set -eu

export FRAPPE_URL="${FRAPPE_URL:-http://backend:8000}"
export FRAPPE_SITE_NAME="${FRAPPE_SITE_NAME:-vendors.localhost}"

echo "Waiting for Frappe at ${FRAPPE_URL}..."
i=0
while true; do
  if node -e "
    fetch(process.env.FRAPPE_URL + '/api/method/ping', {
      headers: { 'X-Frappe-Site-Name': process.env.FRAPPE_SITE_NAME || 'vendors.localhost' }
    }).then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))
  "; then
    break
  fi
  i=$((i + 1))
  if [ "$i" -gt 90 ]; then
    echo "Timed out waiting for Frappe"
    exit 1
  fi
  sleep 5
done

echo "Starting Vendor Directory UI (login-based auth → ${FRAPPE_URL})"
exec node server.js
