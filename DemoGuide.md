# Conversational Analytics Showcase — Demo Guide

<p align="center">
  <img src="https://www.gstatic.com/images/branding/googlelogo/svg/googlelogo_clr_74x24px.svg" alt="Google Cloud" width="120" />
</p>

> [!NOTE]
> This demo guide contains the information Googlers need to reuse the demo. Be sure to review all contents in this doc, before reaching out to the Demo Lead.

> [!IMPORTANT]
> **Please be advised: this is a product in preview; users may occasionally encounter bugs and instability!**

---

## Demo Info

| Field | Value |
| :--- | :--- |
| **Demo Lead** | Gilberto Gutierrez (`gilgtz@google.com`) |
| **Duration** | ~3-5 mins |

---

## Demo Overview

| Why should the audience care? |
| :--- |
| Conversational Analytics is a chat-with-your-data feature powered by Gemini. It empowers business and non-technical retail users (like store managers, category planners, or executives) to query cloud data warehouses directly in regular, natural language, receiving instant structured insights and interactive visualizations (Vega charts) without writing SQL or waiting on analytics teams. |

---

## Demo Script

| Steps <br>*(Attendees see on screen)* | Say <br>*(Demo conductor says)* | Notes/Visual Aids |
| :--- | :--- | :--- |
| **1. Access the Portal & Sign In** | "Welcome to the Conversational Analytics Showcase. We'll start by logging in. Depending on our deployment configuration, we can enable a strict Googler-only login facade or leave it public-facing to showcase external capabilities." | Login screen containing the 'Sign in with Google' button. |
| **2. Interactive Onboarding Tour** | "As a first-time user, we are greeted by an automated 12-step guided tour. This highlights the layout, brand controls, settings gear, and navigation paths so any stakeholder can find their way." | Tooltip overlay pointing to the Brand Selector. |
| **3. Brand Customization** | "To personalize the experience, we can toggle our retail brand workspace (e.g., Home Depot, Target, or Tractor Supply). The dashboard fluidly shifts colors, logos, and presets to fit the brand." | UI colors and logos changing dynamically upon brand selection. |
| **4. Explain System Architecture** | "Let's click 'Show Architecture' in the header. Pointing this out reveals our simplified 4-node flow: BigQuery (Data Storage), Dataplex (Knowledge Catalog), FastAPI/Gemini (Reasoning Engine), and React (Custom UI). Click any node to drill down into the technical orchestration details." | Interactive architecture modal with animated pulsing nodes. |
| **5. Start Demo Walkthrough** | "To make running the demo frictionless, we have an interactive 4-step demo walkthrough that guides us on choosing agents and sending queries." | Demo walkthrough panel pointing to the next actions. |
| **6. Select Agent & Thinking Mode** | "We select our retail agent and toggle on 'Detailed Reasoning Mode' so we can watch the agent formulate its answer step-by-step." | Agent dropdown and Detailed Reasoning Mode toggle highlighted. |
| **7. Ask a Question** | "Let's submit a natural question: *'What was the revenue of Tractor Supply last quarter?'* or click one of our preset questions." | Chat input containing the typed question. |
| **8. Analyze SQL & Charts** | "The reasoning engine automatically translates the question, queries BigQuery, and returns the generated SQL query accompanied by an interactive Vega chart and tabular data grid." | Rendering of the SQL block and the interactive Vega bar chart. |
| **9. Review Executive Insights** | "Immediately below the visualization, the agent generates key business insights summarizing the findings for quick executive consumption." | Layout-aligned insights card displaying key summaries. |
| **10. Key Takeaways** | "This showcase proves how quickly we can orchestrate conversational interfaces over BigQuery, leveraging Gemini, metadata schemas, and beautiful frontends to deliver instant business value." | Key Value Prop: Talk to your data, manage agents, and visualize results. |

---

## Access Control & Internal Publishing Guidelines

### 🔒 Restricting Access to Googlers & Argolis Users
This application supports both a public-facing configuration and an internal-only facade using environment variables:
- **Backend Enforcements (`backend/auth.py` & `backend/.env`):**
  - Set `RESTRICT_TO_GOOGLE=true` to restrict API verification to `@google.com` and Argolis (`altostrat.com`) accounts. When active, other domain SSO logins are blocked with a `403 Forbidden` error.
  - Set `RESTRICT_TO_GOOGLE=false` to allow public-facing domain access.
- **Frontend Controls (`frontend/src/App.tsx` & `frontend/.env`):**
  - Set `VITE_RESTRICT_TO_GOOGLE=true` to validate email domains client-side, trigger sign-outs on non-matching users, and render a clear access-denied message: `Access restricted to @google.com and Argolis accounts only.`

### 👥 Sharing Demo Artifacts (Viewer Access)
To share this demo with Cloud GTM teams (including FTEs, TVCs, and Interns), you must grant **Viewer** permissions on all related internal artifacts (App, Video, Demo Guide, and Slide Deck) to:
* **Alphabet FTEs**: Alphabet "Viewer" group
* **Alphabet TVCs**: `alphabet-extendedworkforce@google.com` (Viewer)
* **Google Interns**: `googlers-intern@google.com` (Viewer)

### 🚀 Live Hosting & Project Exploration
- **Host Live Application / Shared Project:** File hosting requests via **go/demo-hosting-request**.
- **Automate Deployment:** To link your infrastructure click-to-deploy automated setups, see the guidelines on **go/demo-automation-guide**.
- **Code Migration:** All demo repositories must be migrated from CE Gitlab to the shared internal Cloud GTM GitHub organization. Details can be found at **go/use-gtm-github** and **go/releasing**.
