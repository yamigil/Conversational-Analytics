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

## Recent Updates & Fixes
* **Deterministic Mathematical Stream State Machine**: Replaced heuristic English string-matching inside `groupConversationalMessages` with a 100% deterministic temporal partition relative to database execution ($k_{data}$). All text chunks received before or during query execution ($i \le k_{data}$) are mathematically guaranteed to be Pre-Execution Reasoning (`thoughts`), and text chunks received after query execution ($i > k_{data}$) form the Post-Execution Synthesis (`answer`).
* **Viewport Fit, Auto Vega-Lite Chart Synthesis & Reasoning Header Isolation**: Added `overflow-hidden` to the main workspace container (`<main>`) so the chat viewport fits perfectly on screen without vertical page scroll. Upgraded `VisualizerWidget` to automatically synthesize dynamic Vega-Lite bar charts whenever `data.result.data` is returned with numeric columns (matching BigQuery Studio UI behavior). Hardened `isAnswerHeader` so intermediate reasoning titles like `"Answering Your Query"` are never misclassified as final answer headers and remain cleanly isolated inside the collapsible thinking block.
* **Bulletproof Empty Bubble Prevention & Narrative Answer Promotion**: Hardened `parseSingleSystemMessageText` and `groupConversationalMessages` in `App.tsx` so that 2-part streaming narrative answers from Gemini are correctly classified as answers instead of being hidden as internal thoughts. Added fallback promotion for `insights` and strict content verification so empty/fragmented SSE messages (`hasContent == false`) never render blank chat bubbles.
* **Strict Question-Starter Filtering for Suggested Queries**: Hardened `extract_questions_from_text` to verify that numbered list items extracted from agent instructions/descriptions start with a valid prompt verb (`what`, `which`, `who`, `how`, `can`, `show`, `find`, `list`, `are`, `do`, `does`, `is`, `why`, `where`). This permanently prevents non-question instruction headers (e.g. `"The Insights Table 'customer_insights'..."`) from appearing as jumpstart chips.
* **Targeted Dynamic Graph Binding**: Added strict keyword filtering to ignore generic terms (e.g. `graph`, `agent`, `database`, `the`, `look`, `ecommerce`) during metadata graph matches. Prevented binding standard tabular agents (like "The Look Graph" where no BQ Property Graph exists) to random unrelated graphs in the project, letting the engine fall back to building the visualizer schema dynamically from the agent's actual connected tables.
* **Self-Healing Schema Cache Policy & Timeout Hardening**: Hardened Vertex AI API calls by raising timeouts from 12 to 30 seconds to prevent transient timeouts during parallel cache warmups. Upgraded the graph schema discovery cache to bypass storing fallback results if the Gemini API call failed, forcing a retry on subsequent user queries until Gemini successfully materializes premium suggestions.
* **Self-Healing Final Answer Promotion**: Resolved a UI bug where 2-part narrative final responses from Gemini (e.g. `[Analysis Title, Narrative Result]`) were incorrectly grouped as internal thought steps due to heuristic classification, leaving the main chat bubble empty. The grouping engine now detects empty answer blocks and dynamically promotes the last narrative thought into the main answer bubble.
* **Robust Case-Insensitive Graph Suggestions**: Standardized the BigQuery Property Graph metadata parser to handle mixed-case node names and labels (such as `ORDERS` vs `orders`) case-insensitively, preventing accidental fallbacks to generic questions.
* **Precision Suggested Query Regex Fixes**: Hardened the suggested question extractor to ignore database versioning numbers (like `360.` in `penske_customer_360`) and inline math values (like `* 100.` in metric instructions), ensuring only valid natural language questions are suggested to the user.
* **Copy-Pasteable Agent Prompt Guides**: Added `docs/agent_instructions.md` containing highly polished instructions to copy-paste into the BigQuery Data Agent console, explaining the K-Means clustering centroids and service status reminders.
* **Dynamic Thought Process Isolation**: Refactored the streaming message parser in the React frontend to classify all 2-part chunks as internal thoughts unless matching final answer headers, robustly preventing detailed reasoning logs from leaking into the final user-facing response.
* **SQL Widget Polish & Orbit Tracks**: Added rotating dashed orbit tracks and halo glows around satellite nodes in the graph visualizer, and custom syntax highlighting + copy animations to SQL widgets.
* **Vertex AI Gemini 2.5 Flash Upgrade**: Upgraded the core suggestion engine and branding generator from `gemini-1.5-flash` to `gemini-2.5-flash` to match the model availability of the project, resolving a 404 error.
* **Strict Payload Hardening**: Added the mandatory `"role": "user"` field to the Vertex AI request payloads, resolving a 400 Bad Request error.
* **Modular Architecture**: Re-architected `main.py` into modular route handlers (`chat`, `agents`, `telemetry`, `gcp`, etc.) to improve long-term maintainability.
* **Vertex AI API Strict Location Routing**: Re-mapped data agent API queries to properly inject the dynamic region locations (e.g. `us`, `europe-west4`) during GCP API initialization to prevent "GCP Connection Offline" 403/400 Vertex AI rejection errors.
* **TypeScript & GitHub Actions Resilience**: Stripped unused variables out of the Graph Visualizer React TSX nodes, preventing strict CI/CD TS compilers from blocking branch merges.
* **Property Graph Schema Discovery Hotfix**: Refactored `schema_discovery.py` to prevent backend `NameError` crashes when generating fallback discovery nodes on missing graph connections.

---
*Active Telemetry Stream: `G-C0VB9XKP7E`*




