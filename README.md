# Conversational Analytics Agent Web App

A premium, glassmorphic conversational interface for querying and visualizing advertising performance data from Google Cloud BigQuery.

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
├── README.md         # Project documentation (this file)
└── gemini.md         # Session histories and feature rollouts summary
```

## Getting Started (Local Development)

To spin up both the backend API and the frontend dashboard development servers concurrently, run the helper script from the root directory:

```bash
./run.sh
```

The application will be available locally at `http://localhost:8000/`.

### Local Sandbox Mode (Mock Authentication)
To run and test changes locally without hitting Firebase authentication screens, you can enable Mock Auth:
1. Set `MOCK_AUTH=true` inside `backend/.env`.
2. Set `VITE_MOCK_AUTH=true` inside `frontend/.env`.
3. Restart the dev servers. The portal will automatically load a mock user profile (`admin@gilgtz.altostrat.com`) and bypass all SSO login overlays.

---

## Continuous Deployment (CI/CD)

The project includes a unified deployment workflow in `.github/workflows/firebase-deploy.yml`. Every commit pushed to the `main` branch automatically builds and deploys both services:
1. **React Static Assets**: Compiled and uploaded to Firebase Hosting global CDN.
2. **FastAPI Container**: Packaged and deployed to Google Cloud Run.

### Required Deployment Service Account Roles
To support automated builds, your deployment service account (`demoportal@...`) requires the following IAM permissions:
* **Cloud Run Developer** (`roles/run.developer`): Deploy revisions to Cloud Run.
* **Cloud Build Editor** (`roles/cloudbuild.builds.editor`): Build Docker container images.
* **Storage Admin** (`roles/storage.admin`): Upload source bundles to Cloud Storage.
* **Artifact Registry Writer** (`roles/artifactregistry.writer`): Push container artifacts.
* **Service Account User** (`roles/iam.serviceAccountUser`): Bind runtime identity to the service.
* **Firebase Hosting Admin** (`roles/firebasehosting.admin`): Upload assets to CDN.

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

3. **Whitelist Domain**:
   If using Google SSO login, add your live Cloud Run URL (e.g. `https://ca-analytics-portal-xxxxx.run.app`) to your **Firebase Console ➔ Authentication ➔ Settings ➔ Authorized Domains** whitelist!

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

## Key Features

1. **Brand-Tailored Aesthetics**: Beautiful, dark glassmorphic layouts customized for retail brands (Home Depot, Target, and Tractor Supply Co.).
2. **Unified Global Header**: A static top-bar housing your corporate identity, settings gear, sign-out button, connection state, and a context-aware *Show Architecture* button.
3. **Logo-Integrated Home Button**: Clickable brand logo and title in the header that serving as the universal navigation to the home dashboard.
4. **Self-Healing Auth Recovery Loop**: Automatically intercepts expired Google Cloud credentials (`401` errors) or page-refresh token clearance and triggers the Google SSO popup to refresh the token, transparently retrying the failed request in the background.
5. **Interactive Visualizer**: Dynamic rendering of SQL scripts and Vega chart visualizers based on the returned query data.
6. **Layout-Aligned Insights**: Contextual takeaways and summaries positioned below data grids and charts.
7. **Google Image Search Branding**: Instantly search and retrieve corporate logos via Google Search to apply custom visual themes, HSL colors, welcome messages, and layout configurations.
8. **Consolidated Dashboard Layout**: Unified dashboard workspace featuring a clean, centralized "Launch Conversational Analytics" CTA embedded directly inside the Executive Insights card's empty state.
9. **Fixed-Position Onboarding Tour**: A viewport-immune 12-step guided tour with fixed tooltips and automatic alignment offsets pointing to portal controls, branding search selectors, and live previews.
10. **State-Persistent Navigation**: The active page and settings tab state are automatically persisted in the browser session, preventing redirects back to the home page upon manual browser refresh.
11. **Automated Multi-Service CD Pipeline**: GitHub Actions automatically deploys React static assets to Firebase Hosting and FastAPI backend containers to Google Cloud Run on every push to main.
12. **Multi-Source Telemetry & Audit Logs**: Integrates Google Analytics (GA4) for frontend clickstream logs, Firestore for portal administrative audit trails (logins, branding selections), and BigQuery for conversational API chat logs.

---
*Active Telemetry Stream: `G-C0VB9XKP7E`*



