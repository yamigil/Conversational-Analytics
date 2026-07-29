# CA Agent Web App - Project & Session Memory

## Core Architecture & Purpose
A customizable, white-label React + FastAPI frontend template that allows Customer Engineers (and non-CEs) to showcase the power of BigQuery Data Agents, Knowledge Catalog, and Conversational Analytics to both technical and business audiences.
- **Backend:** FastAPI service in `backend/` connecting to Google Cloud `geminidataanalytics` API (Conversational Analytics).
- **Frontend:** React, Vite, and Tailwind CSS dashboard in `frontend/`.
- **Local Startup:** `./run.sh` launches backend on port 8000 and static serving (or `npm run dev` in `frontend/` for Vite on port 5173).

## Key Features & Production Enhancements (PRs #64–#78)
1. **Executive Total SLA Badge & Per-Turn Telemetry Isolation (PRs #71–#78):** Streamlined the OpenTelemetry Trace Inspector into a clean 3-node CA API chat roundtrip flow (`Frontend Portal ➔ Conversational Analytics Engine ➔ BigQuery Engine`). Bound per-turn latencies directly to `RightPanel.tsx` with fallback reconstruction when `list_messages` returns 0 messages. Keyed Free Form sessions dynamically by table ID, returning empty spans when 0 questions are asked to eliminate stale trace leaks.
2. **Strict Database Metric Grounding for AI Chips (PR #70):** Enforced strict grounding rules in `backend/schema_discovery.py` so AI suggestion chips never invent hypothetical features or external tools, grounding 100% on measurable database columns.
3. **Per-Turn Graph Lineage Highlighting (PR #69):** Fixed turn message grouping in `App.tsx` so `sysMsgs` captures turn system messages when `userMessage` and `systemMessage` share the same turn item, lighting up queried tables in emerald green on per-turn lineage inspection.
4. **Self-Healing Answer Shield & Immediate Auto-Refresh (PR #68):** Added narrative text fallback in `App.tsx` and immediate post-stream `fetchMessages()` auto-refresh to eliminate blank response bubbles during live streaming.
5. **Brand-Neutral Dynamic Suggestion Templates (PRs #65 & #67):** Replaced hardcoded fallback strings with dynamic string-interpolated templates in `backend/schema_discovery.py`.
6. **Obsolete Config Cleanup (PR #64):** Removed obsolete `quickstart_secrets` fallback path (`~/Documents/Google/.../secrets.toml`) from `backend/config.py`.

## Quick Dev Commands
- Run `./run.sh` from project root (or `npm run dev` inside `frontend/`).
- Build frontend: `cd frontend && npm run build`.
