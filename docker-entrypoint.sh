#!/bin/bash
set -e

if [ "$1" = "api" ]; then
    exec uvicorn src.main:app --host "${API_HOST}" --port "${API_PORT}"
elif [ "$1" = "worker" ]; then
    exec python -m src.worker
else
    echo "Invalid command. Use 'api' or 'worker'"
    exit 1
fi
