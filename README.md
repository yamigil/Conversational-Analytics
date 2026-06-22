# BigQuery Conversational Analytics: Showcase Hub

**Talk to your data like you talk to a coworker. Powered by Gemini, directly on BigQuery.**

A customizable, white-label frontend template that allows Customer Engineers to easily embed and showcase the power of BigQuery Data Agents, Knowledge Catalog, and Conversational Analytics to both technical and business audiences without building a custom frontend from scratch.

This demo highlights Conversational Analytics (CA) on BigQuery data warehouses, powered by Gemini for Google Cloud. Its purpose is to show how non-technical users can move beyond static dashboards to engage directly with raw enterprise data using natural language. Run forecasting out-of-the-box using built-in database machine learning models (like TimesFM and Contribution Analysis), and verify results instantly with step-by-step thinking logs.



## Directory Structure

```
ca-agent-web-app/
├── backend/          # Python FastAPI service connecting to the Conversational Analytics API
├── frontend/         # React, Vite, and Tailwind CSS dashboard
├── Dockerfile        # Production multi-stage container build configuration
├── firebase.json     # Firebase Hosting rewrite and routing configuration
├── .firebaserc       # Firebase project binding configuration
├── .dockerignore     # Docker build context exclusion rules
├── .gcloudignore     # gcloud deployment upload exclusion rules
├── run.sh            # Root shell script to start both services concurrently for local dev
└── README.md         # Project documentation (this file)
```

## Getting Started (Local Development)

To spin up both the backend API and the frontend dashboard development servers concurrently, run the helper script from the root directory:

```bash
./run.sh
```

The application will be available locally at `http://localhost:8000/`.

### Local Sandbox Mode (Mock Authentication)
To run and test changes locally without requiring external cloud authentication services during offline development, you can enable the Local Sandbox Mode:
1. Set `MOCK_AUTH=true` inside `backend/.env`.
2. Set `VITE_MOCK_AUTH=true` inside `frontend/.env`.
3. Restart the dev servers. The portal will automatically load a mock local user profile (`admin@your-corporate-domain.com`) and initialize the offline development environment.
   * **Simulate External User Profile**: Append `?mock=gmail` to the URL (e.g. `http://localhost:8000/?mock=gmail`) to test domain-restricted settings views and custom onboarding tour flows.

---



## Manual Production Deployment (Alternative)

This application is fully containerized and configured for modern, serverless cloud deployments.

### Option A: Unified Cloud Run Container (Recommended 🏆)
Deploy the entire application (frontend and backend served together) as a single containerized service:

1. **Deploy to Cloud Run**:
   ```bash
   gcloud run deploy ca-analytics-portal \
       --source . \
       --platform managed \
       --region us-central1 \
       --allow-unauthenticated \
       --port 8000
   ```
   *Note: This command uploads under 1MB of source assets and builds the container fresh in the cloud in under 2 minutes.*

2. **Grant IAM Permissions**:
   Go to the **GCP IAM Console** and grant the Cloud Run Default Service Account (`<project-number>-compute@developer.gserviceaccount.com`) the following roles in your target project:
   * **Gemini for Google Cloud User** (required for conversation chat sessions)
   * **Discovery Engine Viewer** (required for Catalog Finder data store searches)



### Option B: Firebase Hosting + Cloud Run (Hybrid CDN)
Deploy the React static assets to Firebase's global edge CDN and automatically rewrite API requests to your Cloud Run backend:

1. **Deploy Backend**: Run the Cloud Run deploy command above to roll out the backend.
2. **Build and Deploy Frontend**:
   ```bash
   # Log in if needed
   firebase login
   
   # Compile and upload frontend assets
   (cd frontend && npm run build)
   firebase deploy --only hosting
   ```
   *Note: Firebase Hosting reads `firebase.json` to serve files from `frontend/dist` and proxy all `/api/**` traffic dynamically to your Cloud Run service.*

---

## Flagship Capabilities

1. **🎨 White-Label Brand Aesthetics**: A gorgeous, premium, dark-mode glassmorphic workspace that dynamically adapts to corporate branding profiles (such as Google Cloud, Home Depot, Target, and Tractor Supply Co.) in real-time.
2. **💬 Conversational Data Analytics (CA)**: Translates natural language business questions into optimized BigQuery SQL queries securely, presenting answers, interactive data grids, and beautiful Vega charts instantly.
3. **🗺️ Interactive System Architecture Modal**: A responsive, animated 4-node data pipeline diagram (BigQuery Storage, Knowledge Catalog, Reasoning Engine, and User Interface) mapping out the entire system's structure.
4. **🧭 Viewport-Immune Onboarding Walkthrough**: A fluid, scroll-tracking interactive tour that smoothly guides first-time users through settings, custom branding, query starters, and conversation history.
5. **📲 Decluttered Mobile-First Experience**: A spacious, mobile-optimized header and sidebar that integrates a centered Agent Selector, a quick-action "New Chat" button, and vertical, downward-flowing architecture connectors.
6. **🔒 Decoupled Auth Recovery & Enterprise Security**: A self-healing authentication loop that transparently catches session expiration and triggers seamless OAuth re-authentication to prevent interruptions.

---
*Active Telemetry Stream: `G-C0VB9XKP7E`*



