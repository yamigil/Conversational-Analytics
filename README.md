# BigQuery Conversational Analytics: Showcase Hub

**Talk to your data like you talk to a coworker. Powered by Gemini, directly on BigQuery.**

A customizable, white-label frontend template that allows Customer Engineers and field teams to embed and showcase BigQuery Data Agents, Knowledge Catalog, and Conversational Analytics without building a custom frontend from scratch.

This portal highlights how enterprise users can engage directly with BigQuery data using natural language, execute built-in statistical analysis, inspect interactive database schema visualizers, and audit execution telemetry in real time.

---

## Directory Structure

```
ca-agent-web-app/
├── backend/          # Python FastAPI service connecting to Conversational Analytics API
├── frontend/         # React, Vite, and Tailwind CSS dashboard
├── Dockerfile        # Production multi-stage container build configuration
├── firebase.json     # Firebase Hosting rewrite configuration
├── run.sh            # Root shell script to start dev servers concurrently
└── README.md         # Project documentation
```

---

## Getting Started (Local Development)

To spin up the backend API and frontend dashboard dev servers concurrently, run:

```bash
./run.sh
```

The application will be available locally at `http://localhost:8000/`.

### Local Sandbox Mode (Mock Auth)
To test locally without external authentication:
1. Set `MOCK_AUTH=true` inside `backend/.env`.
2. Set `VITE_MOCK_AUTH=true` inside `frontend/.env`.
3. Restart dev servers to load the offline development sandbox.

---

## Production Deployment

### Option A: Cloud Run Container (Recommended 🏆)
Deploy the unified backend and static assets as a single Cloud Run container:

```bash
gcloud run deploy ca-analytics-portal \
    --source . \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --port 8000 \
    --min-instances 1 \
    --service-account="demoportal@YOUR_GCP_PROJECT_ID.iam.gserviceaccount.com"
```

### Option B: Firebase Hosting + Cloud Run
Deploy React assets to Firebase Edge CDN with API requests proxied to Cloud Run:

```bash
(cd frontend && npm run build)
firebase deploy --only hosting
```

---

## Key Highlights

1. **🎨 White-Label Branding**: Premium dark-mode glassmorphic workspace that dynamically adapts to corporate branding profiles in real time.
2. **💬 Conversational Analytics (CA)**: Translates natural language questions into optimized BigQuery SQL queries, returning answers, interactive data grids, and adaptive Recharts visualizations.
3. **⚡ Free Form Mode (`inline_context`)**: Ad-hoc exploration on any BigQuery table ID (`project.dataset.table`) with AI-generated starter questions.
4. **🔍 OpenTelemetry Trace Inspector**: Interactive 3-node architecture flowchart (`Frontend ➔ Conversational Analytics Engine ➔ BigQuery Engine`) displaying system instructions, byte billing, and per-turn latency breakdowns.
5. **🗺️ Interactive Schema Visualizer**: Hardware-accelerated 2D SVG canvas for inspecting database relationships, property graph topologies, and per-turn query lineage highlighting.
