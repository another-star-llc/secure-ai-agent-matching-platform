#!/bin/bash
# Wait for backend services before starting nginx

wait_for_port() {
    local port=$1
    local max_attempts=60
    local attempt=1

    while ! (echo > /dev/tcp/127.0.0.1/$port) 2>/dev/null; do
        if [ $attempt -ge $max_attempts ]; then
            echo "Port $port not ready after $max_attempts seconds"
            return 1
        fi
        sleep 1
        attempt=$((attempt + 1))
    done
    return 0
}

echo "Waiting for backend services..."
wait_for_port 8000 && echo "Port 8000 ready"
wait_for_port 8001 && echo "Port 8001 ready"
wait_for_port 8002 && echo "Port 8002 ready"

echo "All backends ready, starting nginx..."
exec /usr/sbin/nginx -g "daemon off;"
