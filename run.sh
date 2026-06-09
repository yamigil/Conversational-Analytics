#!/bin/bash
set -e

# Resolve script directory path
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=================================================="
echo " Starting Conversational Analytics Web Showcase "
echo "=================================================="

# Check virtual environment
if [ ! -d "backend/.venv" ]; then
    echo "Error: backend/.venv not found. Running setup..."
    python3 -m venv backend/.venv
    backend/.venv/bin/pip install -r backend/requirements.txt --index-url https://pypi.org/simple
fi

# Build React frontend assets if dist doesn't exist
if [ ! -d "frontend/dist" ] && command -v npm &> /dev/null; then
    echo "Building React static distribution..."
    (cd frontend && npm run build)
fi

# Run FastAPI backend server
echo "Launching server on http://localhost:8000..."
cd backend
.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
