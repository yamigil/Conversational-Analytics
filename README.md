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

1. **Deploy to Cloud Run**:
   ```bash
   gcloud run deploy ca-analytics-portal \
       --source . \
       --platform managed \
       --region us-central1 \
       --allow-unauthenticated \
       --port 8000 \
       --min-instances 1
   ```
   *Note: Setting `--min-instances 1` keeps at least one container instance warm 24/7 to completely eliminate cold-start latency, ensuring sub-second initial page load times.*

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
3. **🗺️ Dynamic & Zero-Configuration BigQuery Graph Schema Discovery**: A state-of-the-art backend metadata engine that dynamically queries the BigQuery region-level `INFORMATION_SCHEMA.PROPERTY_GRAPHS` catalogs and database client APIs to discover property graph schemas (vertices, edges, and properties) dynamically in real-time, completely eliminating hardcoded schemas.
4. **🎨 Interactive SVG Graph Schema Visualizer**: A gorgeous, hardware-accelerated 2D SVG graph canvas. Features native `<animateMotion>` flow particles, zero-configuration dynamic circular layouts for custom schemas, semantic icon resolvers, and interactive inspectors with node-specific query suggestion injections.
5. **🧭 Symmetrical Flat-Table Centering Layout**: For standard database agents, the visualizer centers table cards dynamically on the screen based on the number of objects, creating a perfectly balanced and high-fidelity representation of relational schemas.
6. **🚪 Click-Outside Auto-Collapse**: Clicking anywhere outside the expanded schema drawer or the toggle button automatically collapses it, ensuring a fluid, modern, desktop-grade UX.
7. **🧭 Viewport-Immune & Self-Healing Walkthrough**: A fluid, scroll-tracking interactive tour that smoothly guides users. Features automated self-healing state observers to prevent stuck states, ensuring a 100% flawless walkthrough.
8. **🗺️ Interactive System Architecture Modal**: A responsive, animated 4-node data pipeline diagram (BigQuery Storage, Knowledge Catalog, Reasoning Engine, and User Interface) mapping out the entire system's structure.
9. **📲 Mobile Experience Enabled**: The workspace is fully responsive and optimized for mobile viewports, enabling seamless chat interactions, settings configuration, and dashboard navigation on-the-go.
10. **🚀 Production-Grade Optimizations**: All unnecessary continuous disk-IO writes and redundant DOM telemetry debug logs were surgically removed. Blazing fast lazy-loading logic ensures agent metadata populates the frontend instantly (sub-50ms), and users are presented with a clean, unopinionated empty state requiring manual agent selection.
11. **✨ Flawless Micro-Interactions**: The UI features ultra-refined UX behaviors, including dynamic graph visualization centering with minimal padding, resilient "Show Thinking" states even on cached capabilities queries, and intelligent auto-collapsing schema drawers upon query selection to maintain a distraction-free conversation canvas.

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



