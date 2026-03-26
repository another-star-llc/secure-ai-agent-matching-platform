#!/bin/bash
set -e

echo "Starting all services..."

# Ensure data directory exists
mkdir -p /app/trusted_agent_store/data

# Inject Firebase config into login.html from environment variables
if [ -f /app/deploy/auth/login.html ]; then
    envsubst '${FIREBASE_API_KEY} ${FIREBASE_AUTH_DOMAIN} ${FIREBASE_PROJECT_ID} ${FIREBASE_STORAGE_BUCKET} ${FIREBASE_MESSAGING_SENDER_ID} ${FIREBASE_APP_ID} ${FIREBASE_MEASUREMENT_ID}' \
        < /app/deploy/auth/login.html > /app/deploy/auth/login.html.tmp \
        && mv /app/deploy/auth/login.html.tmp /app/deploy/auth/login.html
    echo "Firebase config injected into login.html"
fi

# Start supervisord (manages nginx + all services)
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
