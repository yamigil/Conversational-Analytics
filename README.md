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

---



## Manual Production Deployment (Alternative)

This application is fully containerized and configured for modern, serverless cloud deployments.

### Option A: Unified Cloud Run Container (Recommended 🏆)
Deploy the entire application (frontend and backend served together) as a single containerized service:

1. **Deploy to Cloud Run with Dedicated Service Account (Least Privilege)**:
   We highly recommend deploying the service using a dedicated, custom service account (e.g. `demoportal@...`) rather than the default compute engine service account to adhere to Google Cloud security best practices:
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
   *Note: Setting `--min-instances 1` keeps at least one container instance warm 24/7 to completely eliminate cold-start latency, ensuring sub-second initial page load times.*

2. **Grant Minimal IAM Permissions**:
   Go to the **GCP IAM Console** and grant the dedicated service account the following precise roles in your target project:
   * **Gemini for Google Cloud User** (`roles/cloudaicompanion.user`) — *Required to create conversation sessions and stream chats*
   * **Gemini Data Analytics Data Agent User** (`roles/geminidataanalytics.dataAgentUser`) — *Required to discover and query data agents*
   * **BigQuery User** (`roles/bigquery.user`) — *Required to execute BQ query jobs*
   * **BigQuery Data Editor** (`roles/bigquery.dataEditor`) — *Required to write telemetry logs and read schemas*
   * **Discovery Engine Viewer** (`roles/discoveryengine.viewer`) — *Required for Catalog Finder data store searches*
   * **Cloud Datastore User** (`roles/datastore.user`) — *Required to read/write Firestore audit logs and cache*




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
2. **💬 Conversational Data Analytics (CA)**: Translates natural language business questions into optimized BigQuery SQL queries securely, presenting answers, interactive data grids, and beautiful visualizations instantly.
3. **⚡ Zero-Config "Free Form Mode" (`inline_context`) & AI Starter Cards**: Instant ad-hoc exploration on arbitrary BigQuery table IDs (`project.dataset.table`) without requiring pre-published Data Agents. Features an `/api/sandbox/explore` endpoint that scans `INFORMATION_SCHEMA.COLUMNS` and uses Gemini 2.5 Flash-Lite to dynamically generate column-aware analytical starter cards with shimmer animations in seconds.
4. **🔍 Widescreen OpenTelemetry Trace Inspector**: An interactive 5-node architecture flowchart (`Frontend ➔ Data Agent Engine ➔ CA API Service ➔ Gemini Engine ➔ BigQuery Executor`) with a widescreen toggle (`[↔]`). Developers and architects can inspect real-time system instruction extractions directly from GCP, real-time BigQuery job byte billing (e.g. `10.0 MB` billed), and isolate telemetry down to individual questions via an interactive Per-Turn Switcher (`💬 Filter by Turn`).
5. **📊 Adaptive Recharts Visualization Engine**: Replaces static charts with interactive SVG Recharts featuring glowing vertical gradient fills (`#8b5cf6` to `#3b82f6`), rounded bar corners, and dark glassmorphic tooltips. Automatically detects nominal vs quantitative fields, skips constant grouping columns (e.g. `agent = 'bq_multi_agent'`), and pivots multi-series rows cleanly with an interactive `<Legend />` and chart morphing (`[📊 Bar]`, `[📈 Line]`, `[📉 Area]`).
6. **🗺️ Dynamic & Zero-Configuration BigQuery Graph Schema Discovery**: A state-of-the-art backend metadata engine that dynamically queries the BigQuery region-level `INFORMATION_SCHEMA.PROPERTY_GRAPHS` catalogs and database client APIs to discover property graph schemas (vertices, edges, and properties) dynamically in real-time, completely eliminating hardcoded schemas.
7. **🎨 Interactive SVG Graph Schema Visualizer**: A gorgeous, hardware-accelerated 2D SVG graph canvas. Features native `<animateMotion>` flow particles, zero-configuration dynamic circular/ellipse layouts for custom schemas, semantic icon resolvers, orbiting satellite record nodes with live property inspectors, and interactive node-specific query suggestion injections.
8. **🧭 Symmetrical Flat-Table Centering Layout**: For standard database agents, the visualizer centers table cards dynamically on the screen based on the number of objects, creating a perfectly balanced and high-fidelity representation of relational schemas.
9. **🚪 Click-Outside Auto-Collapse**: Clicking anywhere outside the expanded schema drawer or the toggle button automatically collapses it, ensuring a fluid, modern, desktop-grade UX.
10. **🧭 Viewport-Immune & Self-Healing Walkthrough**: A fluid, scroll-tracking interactive tour that smoothly guides users. Features automated self-healing state observers to prevent stuck states, ensuring a 100% flawless walkthrough.
11. **🗺️ Interactive System Architecture Modal**: A responsive, animated 4-node data pipeline diagram (BigQuery Storage, Knowledge Catalog, Reasoning Engine, and User Interface) mapping out the entire system's structure.
12. **📲 Mobile Experience Enabled**: The workspace is fully responsive and optimized for mobile viewports, enabling seamless chat interactions, settings configuration, and dashboard navigation on-the-go.
13. **🚀 Production-Grade Optimizations & Hardened SSE Streams**: All unnecessary continuous disk-IO writes and redundant DOM telemetry debug logs were surgically removed. Blazing fast lazy-loading logic populates agent metadata instantly (sub-50ms), and a deterministic temporal stream parser separates intermediate chain-of-thought reasoning into a clean collapsible drawer while protecting summary insights.

---

## 🗺️ Interactive SVG Graph Schema Visualizer

For data agents connected to a **BigQuery Graph database**, the portal replaces the standard welcoming text with an immersive, interactive 2D database relationship map:

### Key Features:
*   **Real-Time Database Schema Discovery**: Connects to the active BigQuery project using gcloud Application Default Credentials (ADC) and the Google Cloud BigQuery client to fetch dataset location APIs and regional SQL metadata. Automatically parses the property graph's parsed JSON metadata (nodes, edges, labels, keys) dynamically, styling them and loading them into the visualizer instantly. Falls back to local curated presets if the database is offline or sandbox mode is active.
*   **Automatic Graph Separation**: Automatically detects whether an agent is a property graph agent or a relational flat-table agent (matching keywords like `"graph"`, `"penske"`, or `"customer 360"`), ensuring the correct visual representation is displayed instantly.
*   **Hardware-Accelerated Flow Particles**: Uses native SVG `<animateMotion>` elements to run smooth 60fps flowing energy particles along connection tracks, indicating the direction of database relationships without consuming any JavaScript main thread cycles.
*   **Zero-Configuration Symmetrical Layouts**:
    *   *Showcase Flagship (The Look Ecommerce)*: Automatically aligns nodes in a highly readable symmetrical butterfly coordinate layout (Users and Orders on the left, Brands and Stores on the right, Products in the center).
    *   *Adaptive Circular Fallback (CE Custom Agents)*: If a Customer Engineer connects a brand-new custom graph agent, the engine automatically calculates polar trigonometry coordinates ($\theta_i = \frac{2\pi i}{N}$) to distribute nodes symmetrically in an overlap-free circle.
*   **Semantic Icon Resolver**: Scans node names for industry keywords (e.g. `users`, `sessions`, `pageviews`, `transactions`, `cards`, `revenue`, `db`) and dynamically resolves them to highly relevant Lucide icons.
*   **Vibrant Multi-Color Identity**: Cycles through a curated 8-color neon palette based on node indices, assigning a distinct visual color theme to every node type.
*   **Focused Interactivity & Query Injections**: Clicking a node dims the rest of the canvas, highlights its active relationship edges, and opens a glassmorphic inspector card displaying the entity description and curated question cards. Clicking any question instantly populates the chat input box.
*   **On-Demand Blazing Fast Loading**: By bypassing database discovery operations in initial API calls and moving them to asynchronous on-demand schema routes, agent lists load into the dropdown natively in under 35 milliseconds.

---
*Active Telemetry Stream: `G-C0VB9XKP7E`*




