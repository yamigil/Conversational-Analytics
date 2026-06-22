# BigQuery Conversational Analytics: Showcase Hub

**Talk to your data like you talk to a coworker. Powered by Gemini, directly on BigQuery.**

A customizable, white-label frontend template that allows Customer Engineers to easily embed and showcase the power of BigQuery Data Agents, Knowledge Catalog, and Conversational Analytics to both technical and business audiences without building a custom frontend from scratch.

This demo highlights Conversational Analytics (CA) on BigQuery data warehouses, powered by Gemini for Google Cloud. Its purpose is to show how non-technical users can move beyond static dashboards to engage directly with raw enterprise data using natural language. Run forecasting out-of-the-box using built-in database machine learning models (like TimesFM and Contribution Analysis), and verify results instantly with step-by-step thinking logs.

## Dual-Purpose Architecture

This codebase is engineered to support a dual-purpose deployment strategy:
1. **💼 Internal Enterprise Portal**: Designed for secure internal corporate deployments. It leverages corporate Single Sign-On (SSO) and Google Service Accounts (ADC) to enable Customer Engineers and internal teams to securely query and manage high-fidelity data warehouses.
2. **🚀 External Public Showcase Portal**: Designed for public demonstrational access. It utilizes a secure, domain-filtered sandbox mode that automatically isolates external public traffic (e.g. restricting access to specific sandbox domains like `@gmail.com` to demonstrate multi-tenant sandbox capabilities) while presenting a simplified, branding-only layout to showcase features to external stakeholders.

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

## Continuous Deployment (CI/CD) & Multi-Site Architecture

The project is equipped with a robust, **unconditional (zero-skip) multi-site deployment pipeline** configured via two separate GitHub Action workflows. To eliminate synchronization gaps and deployment blocking (a common failure mode in multi-branch configurations where filters skip steps when branches are synced), the workflows are designed to unconditionally compile, build, and deploy all frontend and backend services on every push:

### 💼 A. Corporate Portal (https://your-corporate-domain.com/)
* **Branch**: `main`
* **Workflow**: `.github/workflows/firebase-deploy.yml`
* **Behavior**: Deploys the corporate portal with standard enterprise domain authentication restrictions (`@google.com` and `@your-corporate-domain.com`).
* **Hosting Target**: `corporate` (mapping to your production site `your-gcp-project-id` in Firebase).

### 🚀 B. Public Showcase Portal (https://your-showcase-domain.com/)
* **Branch**: `showcase`
* **Workflow**: `.github/workflows/firebase-deploy-showcase.yml`
* **Behavior**: Deploys a public showcase portal tailored for external demonstrational access. It enforces a **domain-based access filter** (restricting access to specific email domains like `gmail.com` to demonstrate external sandbox capabilities) using a dual-layer check: backend container environment `ALLOWED_DOMAINS=gmail.com` and frontend compile-time `VITE_ALLOWED_DOMAINS="gmail.com"` to automatically validate incoming identities.
* **Hosting Target**: `showcase` (mapping to your public showcase hosting site `your-showcase-site-id` in Firebase).
* **First-Party Authentication**: To ensure seamless authentication flow under browser privacy protections (preventing cross-site cookie blocks and automatic session drops on macOS/Safari), the showcase build maps `VITE_FIREBASE_AUTH_DOMAIN` directly to `"your-showcase-domain.com"`.
  * *Note: The redirect URI `https://your-showcase-domain.com/__/auth/handler` must be whitelisted in your GCP project's OAuth 2.0 Client ID settings!*

### Required Deployment Service Account Roles
To support automated builds, your deployment service account (`your-service-account@your-project-id.iam.gserviceaccount.com`) requires the following IAM permissions:
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
7. **Wikipedia/Wikidata Logo Search & SVG Branding**: Instantly search and retrieve official corporate logos directly from Wikipedia/Wikidata using an automated image-scoring fallback system. Default Google Cloud presets use a high-fidelity, transparent vector SVG to ensure premium dark-mode presentation.
8. **Consolidated Dashboard Layout**: Unified dashboard workspace featuring a clean, centralized "Launch Conversational Analytics" CTA embedded directly inside the Executive Insights card's empty state.
9. **Viewport-Immune Onboarding Tour & Interactive Walkthrough**: A viewport-immune 13-step guided tour and 5-step interactive Demo Walkthrough featuring:
   * **Fluid Scroll-Tracking**: Tooltips stick in real-time to highlighted elements as the user scrolls the page or nested scrollable panels (using capture-phase event interceptors).
   * **Adaptive Boundary-Clipping Fading**: Tooltips smoothly fade out (`opacity: 0`) when target elements enter a 30px boundary zone near viewport or scroll edges, preventing screen crowding and input overlap. They instantly fade back in and align perfectly when scrolled back into view.
   * **Late-Render Catcher**: Automatically catches late-rendered DOM elements after page transitions or modal actions, using calibrated vertical offsets (`64px` header height) to display tooltips instantly without requiring manual scrolling.
   * **Targeted Highlight Isolation**: Distinguishes between full-panel sidebar highlights (Step 10, Manage History) and precise button highlights (Step 16, Clean Slate) for a highly polished, professional onboarding experience.
10. **State-Persistent Navigation**: The active page and settings tab state are automatically persisted in the browser session, preventing redirects back to the home page upon manual browser refresh.
11. **Automated Multi-Service CD Pipeline**: GitHub Actions automatically deploys React static assets to Firebase Hosting and FastAPI backend containers to Google Cloud Run on every push to main.
12. **Multi-Source Telemetry & Audit Logs**: Integrates Google Analytics (GA4) for frontend clickstream logs, Firestore for portal administrative audit trails (logins, branding selections), and BigQuery for conversational API chat logs.
13. **Simplified System Architecture Diagram**: A re-designed 4-node flow (BigQuery Storage, Knowledge Catalog, Reasoning Engine, and Custom UI) with interactive pulsing tags directing users to click nodes for detailed component breakdowns.
14. **Dynamic Connection & Region Override Selector**: A live top-right connection dropdown allowing corporate (Altostrat) users to override active credential modes (Service Account vs. SSO User Session), switch target GCP projects, and dynamically select GCP locations (regions) on-the-fly, instantly hot-reloading data agents and session catalogs.
15. **Premium Query Starters Landing Page**: A sleek, dynamic chat landing screen featuring a personalized greeting and a grid of brand-specific query starter cards that instantly populate the chat and trigger database queries to ensure a seamless "cold-start" experience.
16. **SSO-Isolated Connection Overrides**: Under Service Account (ADC) credentials mode, the frontend strictly isolates and bypasses local-storage project and location header overrides, ensuring corporate sandbox users (`@altostrat.com`) and public facade users enjoy seamless, unified connectivity out-of-the-box.
17. **Container-Native Firebase Auth Resolution**: The backend utilizes GCP default credential chains to dynamically query the container's active Google Cloud metadata server at runtime, automatically resolving the Firebase project ID to prevent 401 token authentication errors in serverless hosting (like Cloud Run) while maintaining 100% white-label security compliance.
18. **Decoupled Walkthrough Fail-Safe & Streaming Diagnostics**: The onboarding Demo Tour features a decoupled, robust fail-safe mechanism that guarantees the gold-glowing "Show thinking" button and step-by-step reasoning logs are always visible and interactive, even if the backend returns custom stream statuses or empty thought arrays.
19. **White-Label Clean Slate**: Complete repository purification, removing obsolete legacy static files (such as `UserGuide.html` and developer-facing guide fragments) to ensure 100% clean, professional white-label presentations.
20. **Responsive Mobile Onboarding Welcome Modal**: Replaced the desktop-focused "New here?" onboarding walkthrough trigger with a mobile-optimized centered modal explaining that the full interactive walkthrough is best experienced on a desktop, storing user preference and leaving a clean mobile dashboard.
21. **Recent Conversations Dashboard Grid**: Replaced the legacy AI Insights card on the home dashboard with a premium grid displaying the top 4 most recent chat sessions. Tapping a card loads its history and redirects the user to the chat workspace, while keeping a prominent "Ask a New Question" CTA to start a fresh canvas.
22. **Forced Default GCP Theme on Login**: Forces the initial active session brand key to `"default"` on fresh logins to guarantee a standard dark Google Cloud theme, while fully preserving the user's ability to live-preview, edit, and save custom branding profiles during their session.
23. **Centered Mobile Agent Selector Card**: Injects a beautiful, centered glassmorphic card on mobile viewports when the chat workspace is in its empty welcome state, enabling effortless agent selection and discovery for mobile users without needing the sidebar.
24. **Mobile-Only New Chat Header Button**: Adds a compact header button in the mobile chat workspace that lets users instantly clear their active session and return to the welcome screen in a single tap.
25. **Real-Time Context-Aware Agent Suggestions**: Swaps the suggested query starter cards in real-time as the user switches agents, serving GA4 marketing questions for the Marketing Agent and retail-specific questions for the Retail Agent.
26. **Responsive Architecture Flow Connectors**: Restructured the "System Architecture & Orchestration" modal so that the connector tracks and moving particles flow vertically downwards between stacked nodes on mobile viewports, matching the screen layout perfectly.
27. **Decluttered Mobile Header Banner**: Relocated secondary actions (Show Architecture and Sign Out) to the bottom of the mobile sidebar, leaving the header clean and spacious.

---
*Active Telemetry Stream: `G-C0VB9XKP7E`*



