# ==================================================
# Stage 1: Build the React frontend
# ==================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ==================================================
# Stage 2: Serve with FastAPI Python backend
# ==================================================
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies (if any needed for builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt --index-url https://pypi.org/simple

# Copy compiled frontend distribution assets
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Copy backend application code
COPY backend/ /app/backend/

# Set working directory to backend so Python paths resolve correctly
WORKDIR /app/backend

# Expose port (Cloud Run will override this via the PORT environment variable)
EXPOSE 8000

# Start the uvicorn server dynamically on the specified port
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
