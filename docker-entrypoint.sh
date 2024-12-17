#!/bin/bash
set -e

if [ "$1" = "api" ]; then
    exec uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
elif [ "$1" = "worker" ]; then
    exec python -m src.worker
else
    echo "Invalid command. Use 'api' or 'worker'"
    exit 1
fi
