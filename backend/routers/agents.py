import os
import json
import logging
import requests
import re
from fastapi import APIRouter, HTTPException, Body, Depends, Header, Response, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from firebase_admin import firestore
from google.cloud import bigquery
from ca_client import ConversationalAnalyticsClient
from auth import get_current_user, get_analytics_client
from google.api_core import exceptions as google_exceptions
from schema_discovery import get_schema_summary
from bq_client import get_live_table_preview
from config import logger, get_project_id, DELETED_CONVOS_FILE, get_deleted_conversations, add_deleted_conversation, BRANDING_FILE
import time

router = APIRouter()


@router.get("/api/agents")
def get_agents(user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        agents = client.list_agents()
        

            
        enriched = [enrich_agent_metadata(agent, skip_db_scan=True) for agent in agents]
        return enriched
    except Exception as e:
        handle_route_exception(e, "list data agents")


@router.get("/api/agents/{agent_name:path}/schema")
def get_agent_schema(agent_name: str, user: dict = Depends(get_current_user), client: ConversationalAnalyticsClient = Depends(get_analytics_client)):
    try:
        logger.info(f"On-Demand Schema Request received for agent: {agent_name}")
        agent = client.get_agent(agent_name)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")
            
        from schema_discovery import enrich_agent_metadata
        enriched = enrich_agent_metadata(agent, skip_db_scan=False)
        return enriched
    except Exception as e:
        handle_route_exception(e, "load agent schema details")



@router.get("/api/preview")
def get_table_preview(
    table_name: str,
    agent_name: Optional[str] = None,
    x_gcp_user_token: Optional[str] = Header(None),
    user: dict = Depends(get_current_user),
    client: ConversationalAnalyticsClient = Depends(get_analytics_client)
):
    # 1. Resolve table and dataset names dynamically
    clean_name = table_name.split(".")[-1] if "." in table_name else table_name
    
    dataset_id = None
    project_id = None
    if agent_name:
        try:
            # Fetch agent metadata to find the connected dataset ID and project ID dynamically
            agent = client.get_agent(agent_name)
            da_agent = agent.get("dataAnalyticsAgent", {})
            for context_key in ["publishedContext", "lastPublishedContext", "stagingContext"]:
                context = da_agent.get(context_key, {})
                ds_refs = context.get("datasourceReferences", {})
                bq_ref = ds_refs.get("bq", {})
                table_refs = bq_ref.get("tableReferences", [])
                for t in table_refs:
                    ref_table = t.get("tableId", "")
                    if ref_table == clean_name or t.get("tableId", "").split(".")[-1] == clean_name:
                        dataset_id = t.get("datasetId")
                        project_id = t.get("projectId")
                        break
                if dataset_id:
                    break
            
            # If still not found, check if it is a Graph Agent using dynamic binding!
            if not dataset_id:
                from schema_discovery import enrich_agent_metadata
                enriched_agent = enrich_agent_metadata(agent)
                if enriched_agent.get("isGraphAgent") and "graphData" in enriched_agent:
                    graph_data = enriched_agent["graphData"]
                    if "datasetId" in graph_data:
                        dataset_id = graph_data["datasetId"]
                        project_id = graph_data.get("projectId")
                        logger.info(f"Resolved dataset '{dataset_id}' for graph node preview of table '{clean_name}'")
        except Exception as e:
            logger.warning(f"Could not resolve dataset_id from agent metadata: {e}")
            
    # 2. Fallback to extracting dataset ID from input table string if present
    if not dataset_id and "." in table_name:
        parts = table_name.split(".")
        if len(parts) == 3:
            project_id = parts[0]
            dataset_id = parts[1]
        elif len(parts) == 2:
            dataset_id = parts[0]
            
    if not project_id:
        project_id = get_project_id()
        
    if not dataset_id:
        raise HTTPException(
            status_code=400, 
            detail=f"Could not resolve dataset context for table '{table_name}'. Please ensure agent_name is specified."
        )
        
    # 3. Call our clean, modular live BigQuery preview function (timeout-enforced, 100% live!)
    return get_live_table_preview(project_id, dataset_id, clean_name, user_token=x_gcp_user_token)

import time

def penske_mock_stream_generator(query: str, chat_mode: str):
    """Generates a high-fidelity, paced mock event stream for the Penske Customer 360 Graph Agent.
    Unifies real customer names from the peer's CSV with rich, strategic business use cases.
    """
    q = query.lower()
    
    # 1. Scenario Selection based on keywords
    if "visit" in q or "loyal" in q or "most service" in q or "top customer" in q:
        scenario = "loyalty"
    elif "lease" in q or "trim" in q or "sales" in q or "volume" in q:
        scenario = "sales_volume"
    elif "audit" in q or "jacket" in q or "compliance" in q or "finance" in q:
        scenario = "audit"
    elif "campaign" in q or "marketing" in q or "segment" in q or "warranty" in q:
        scenario = "marketing"
    else:
        scenario = "generic"

    # Step A: Stream Thinking Statuses (Simulating active DB analysis)
    statuses = [
        "Analyzing context",
        "Retrieved context for customer 360 query",
        "Executing Graph MATCH query in BigQuery..."
    ]
    if scenario == "sales_volume":
        statuses.append("Generating bar chart visualization")
    else:
        statuses.append("Compiling structured tabular output")
        
    for status in statuses:
        chunk = {
            "systemMessage": {
                "text": {
                    "parts": ["Analyzing context", status] # status is recognized if first part is a status keyword
                }
            }
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        time.sleep(0.4)

    # Step B: Stream Collapsible Thought Process (Reasoning Log)
    if chat_mode == "thinking":
        if scenario == "loyalty":
            thought_title = "BigQuery GQL Execution Plan"
            thought_body = (
                "1. Traverse relationships: Customer vertex -(OWNS)-> Vehicle vertex -(SERVICED_AT)-> ServiceVisit vertex.\n"
                "2. Filter: Group by customer_id, name, phone, and address.\n"
                "3. Aggregate: COUNT(s.visit_id) to calculate total visits, SUM(s.service_cost) to calculate total spend.\n"
                "4. Sort: Descending by total visits to find the top 5 most loyal customers."
            )
        elif scenario == "sales_volume":
            thought_title = "BigQuery Graph Grouping Plan"
            thought_body = (
                "1. Traverse: Vehicle vertex and extract trim level (SR5, TRD Sport, etc.) and purchase_type (LEASE, RETAIL_BUY).\n"
                "2. Aggregate: Count total units per trim and split by acquisition channel.\n"
                "3. Cross-reference: Match counts against the Q4 2025 and Q1 2026 sales volume summary sheets to ensure consistency."
            )
        elif scenario == "audit":
            thought_title = "F&I Compliance Traversal Plan"
            thought_body = (
                "1. Traverse: Customer vertex -(OWNS)-> Vehicle vertex -(FINANCED_WITH)-> DealJacket vertex.\n"
                "2. Filter: Isolate DealJacket records where status = 'IN_AUDIT'.\n"
                "3. Extract: Pull customer name, phone, vehicle model, trim, finance provider, loan amount, and credit score.\n"
                "4. Goal: Audit compliance rates across different financing channels (supporting Rich's F&I project)."
            )
        elif scenario == "marketing":
            thought_title = "Omnichannel Marketing Segmentation"
            thought_body = (
                "1. Identify: Vehicles out of warranty (Service History mileage > 36,000 miles).\n"
                "2. Correlate: Match these owners against GA4 Web Events where event_type = 'ACCESSORY_SEARCH' or 'TRADE_IN_ESTIMATE'.\n"
                "3. Traverse: Customer -(OWNS)-> Vehicle -(SERVICED_AT)-> ServiceVisit and intersect with Customer -(TRIGGERED)-> WebEvent.\n"
                "4. Generate: A high-propensity target segment for Jessica's personalized rate-card campaigns."
            )
        else:
            thought_title = "Graph Schema Discovery"
            thought_body = "1. Scanning connected graph entities (Customers, Vehicles, Service History).\n2. Writing optimized Graph matching query using MATCH syntax."

        chunk = {
            "systemMessage": {
                "text": {
                    "parts": [thought_title, thought_body]
                }
            }
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        time.sleep(0.8)

    # Step C: Stream Answer and GQL SQL Query
    if scenario == "loyalty":
        answer_text = (
            "To find the top 5 customers with the most service visits, we write a BigQuery Graph query to traverse the relationships from the consolidated customer master records down to the service logs (representing the 'Willow' service advisor database).\n\n"
            "Here is the native BigQuery Property Graph query:\n"
            "```sql\n"
            "SELECT \n"
            "  c.name,\n"
            "  c.phone,\n"
            "  c.address,\n"
            "  COUNT(s.visit_id) AS total_visits,\n"
            "  ROUND(SUM(s.service_cost), 2) AS total_spend\n"
            "FROM \n"
            "  `gilbertos-project-340619.penske_customer_360.customer_360_graph`\n"
            "MATCH (c:Customer)-[:OWNS]->(v:Vehicle)-[:SERVICED_AT]->(s:ServiceVisit)\n"
            "GROUP BY \n"
            "  c.name, c.phone, c.address\n"
            "ORDER BY \n"
            "  total_visits DESC\n"
            "LIMIT 5;\n"
            "```\n"
            "Based on your peer's real Toyota Tacoma service history, here are the top 5 most loyal customers who visited our service bays:"
        )
    elif scenario == "sales_volume":
        answer_text = (
            "I have queried the unified `vehicles` vertex table. By grouping the vehicles by their trim levels and splitting them by their acquisition type (Lease vs. Retail Purchase), we get a clear view of retail and lease originations.\n\n"
            "Here is the BigQuery Graph matching query:\n"
            "```sql\n"
            "SELECT \n"
            "  v.trim,\n"
            "  COUNTIF(v.purchase_type = 'LEASE') AS lease_count,\n"
            "  COUNTIF(v.purchase_type = 'RETAIL_BUY') AS retail_count,\n"
            "  COUNT(v.vin) AS total_units\n"
            "FROM \n"
            "  `gilbertos-project-340619.penske_customer_360.customer_360_graph`\n"
            "MATCH (v:Vehicle)\n"
            "GROUP BY \n"
            "  v.trim\n"
            "ORDER BY \n"
            "  total_units DESC;\n"
            "```\n"
            "Here is the distribution of Tacoma trim levels in your customer database, aligning directly with your dealership group summaries:"
        )
    elif scenario == "audit":
        answer_text = (
            "To audit Penske’s F&I (Finance & Insurance) operations, we traverse the Customer Master Record to their active Deal Jackets that are currently flagged as `IN_AUDIT`. This is the exact use case CIO Rich Hook is implementing to ensure document compliance and streamline back-office audits.\n\n"
            "Here is the BigQuery Graph query:\n"
            "```sql\n"
            "SELECT \n"
            "  c.name,\n"
            "  c.phone,\n"
            "  v.trim,\n"
            "  d.finance_provider,\n"
            "  d.loan_amount,\n"
            "  d.credit_score,\n"
            "  d.status\n"
            "FROM \n"
            "  `gilbertos-project-340619.penske_customer_360.customer_360_graph`\n"
            "MATCH (c:Customer)-[:OWNS]->(v:Vehicle)-[:FINANCED_WITH]->(d:DealJacket)\n"
            "WHERE \n"
            "  d.status = 'IN_AUDIT';\n"
            "```\n"
            "Here are the active deal jackets currently undergoing compliance audits in your database:"
        )
    elif scenario == "marketing":
        answer_text = (
            "By querying the unified Customer 360 Property Graph, we can solve Jessica's (Director of Marketing) core business problem: operationalizing 1st-party data to run targeted campaigns.\n\n"
            "We will isolate customers whose Tacomas have **exceeded their 36,000-mile factory warranty** (siloed in the Service/Willow database) and who have recently **searched for TRD accessories or estimated trade-in values online** (siloed in GA4 web traffic).\n\n"
            "Here is the BigQuery Graph matching query:\n"
            "```sql\n"
            "SELECT \n"
            "  c.name,\n"
            "  c.phone,\n"
            "  c.email,\n"
            "  v.trim,\n"
            "  MAX(s.mileage) AS last_mileage,\n"
            "  e.details AS web_interest\n"
            "FROM \n"
            "  `gilbertos-project-340619.penske_customer_360.customer_360_graph`\n"
            "MATCH (c:Customer)-[:OWNS]->(v:Vehicle)-[:SERVICED_AT]->(s:ServiceVisit),\n"
            "      (c)-[:TRIGGERED]->(e:WebEvent)\n"
            "WHERE \n"
            "  s.mileage > 36000\n"
            "  AND (e.event_type = 'ACCESSORY_SEARCH' OR e.event_type = 'TRADE_IN_ESTIMATE')\n"
            "GROUP BY \n"
            "  c.name, c.phone, c.email, v.trim, e.details\n"
            "ORDER BY \n"
            "  last_mileage DESC;\n"
            "```\n"
            "Here is the high-propensity, out-of-warranty customer segment ready for marketing activation:"
        )
    else:
        answer_text = (
            "Welcome to the Penske Customer 360 Graph Agent! I have queried the unified database. Here are the first few records showing consolidated customer profiles, active vehicle ownerships, and service logs:\n\n"
            "```sql\n"
            "SELECT c.name, v.model, v.trim, COUNT(s.visit_id) AS visits\n"
            "FROM `gilbertos-project-340619.penske_customer_360.customer_360_graph`\n"
            "MATCH (c:Customer)-[:OWNS]->(v:Vehicle)-[:SERVICED_AT]->(s:ServiceVisit)\n"
            "GROUP BY c.name, v.model, v.trim LIMIT 5;\n"
            "```"
        )

    # Stream the answer character-by-character to simulate streaming response
    words = answer_text.split(" ")
    for i in range(0, len(words), 5):
        chunk_text = " ".join(words[i:i+5]) + " "
        chunk = {
            "systemMessage": {
                "text": {
                    "parts": [chunk_text]
                }
            }
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        time.sleep(0.05)

    # Step D: Stream structured Table Data
    if scenario == "loyalty":
        table_payload = {
            "schema": {
                "fields": [
                    {"name": "Name", "type": "STRING"},
                    {"name": "Phone", "type": "STRING"},
                    {"name": "Address", "type": "STRING"},
                    {"name": "Total Visits", "type": "INTEGER"},
                    {"name": "Total Spend", "type": "FLOAT"}
                ]
            },
            "data": {
                "rows": [
                    {"f": [{"v": "Michael Torres"}, {"v": "(208) 134-4152"}, {"v": "9770 1st St, Blackfoot, ID 83221"}, {"v": "3"}, {"v": "269.85"}]},
                    {"f": [{"v": "Sarah Jenkins"}, {"v": "(385) 489-4843"}, {"v": "1685 1st St, Roy, UT 84067"}, {"v": "2"}, {"v": "189.00"}]},
                    {"f": [{"v": "David Chen"}, {"v": "(385) 301-1995"}, {"v": "8089 Oak Ave, Ogden, UT 84401"}, {"v": "2"}, {"v": "204.00"}]},
                    {"f": [{"v": "Emily Rodriguez"}, {"v": "(208) 801-7439"}, {"v": "7729 Main St, Idaho Falls, ID 83401"}, {"v": "2"}, {"v": "170.00"}]},
                    {"f": [{"v": "Robert Campbell"}, {"v": "(385) 316-5859"}, {"v": "7992 Oak Ave, Salt Lake City, UT 84111"}, {"v": "2"}, {"v": "231.50"}]}
                ]
            }
        }
    elif scenario == "sales_volume":
        table_payload = {
            "schema": {
                "fields": [
                    {"name": "Trim Level", "type": "STRING"},
                    {"name": "Leases", "type": "INTEGER"},
                    {"name": "Retail Sales", "type": "INTEGER"},
                    {"name": "Total Units", "type": "INTEGER"}
                ]
            },
            "data": {
                "rows": [
                    {"f": [{"v": "SR5"}, {"v": "21"}, {"v": "42"}, {"v": "63"}]},
                    {"f": [{"v": "TRD Sport"}, {"v": "15"}, {"v": "31"}, {"v": "46"}]},
                    {"f": [{"v": "TRD Off-Road"}, {"v": "10"}, {"v": "25"}, {"v": "35"}]},
                    {"f": [{"v": "SR (Base)"}, {"v": "8"}, {"v": "12"}, {"v": "20"}]},
                    {"f": [{"v": "TRD Pro"}, {"v": "3"}, {"v": "10"}, {"v": "13"}]},
                    {"f": [{"v": "Limited"}, {"v": "3"}, {"v": "5"}, {"v": "8"}]}
                ]
            }
        }
    elif scenario == "audit":
        table_payload = {
            "schema": {
                "fields": [
                    {"name": "Customer", "type": "STRING"},
                    {"name": "Phone", "type": "STRING"},
                    {"name": "Trim Level", "type": "STRING"},
                    {"name": "Finance Provider", "type": "STRING"},
                    {"name": "Loan Amount", "type": "FLOAT"},
                    {"name": "Credit Score", "type": "INTEGER"},
                    {"name": "Audit Status", "type": "STRING"}
                ]
            },
            "data": {
                "rows": [
                    {"f": [{"v": "Emily Rodriguez"}, {"v": "(208) 801-7439"}, {"v": "TRD Off-Road"}, {"v": "Toyota Financial Services"}, {"v": "38500.00"}, {"v": "645"}, {"v": "IN_AUDIT"}]},
                    {"f": [{"v": "Matthew O'Connor"}, {"v": "(435) 270-5636"}, {"v": "Limited"}, {"v": "Chase Auto"}, {"v": "46200.00"}, {"v": "710"}, {"v": "IN_AUDIT"}]},
                    {"f": [{"v": "Rachel King"}, {"v": "(385) 297-8125"}, {"v": "SR5"}, {"v": "Penske Finance"}, {"v": "31800.00"}, {"v": "595"}, {"v": "IN_AUDIT"}]},
                    {"f": [{"v": "Nicole Adams"}, {"v": "(435) 445-2986"}, {"v": "TRD Pro"}, {"v": "Toyota Financial Services"}, {"v": "44900.00"}, {"v": "680"}, {"v": "IN_AUDIT"}]}
                ]
            }
        }
    elif scenario == "marketing":
        table_payload = {
            "schema": {
                "fields": [
                    {"name": "Customer", "type": "STRING"},
                    {"name": "Phone", "type": "STRING"},
                    {"name": "Email", "type": "STRING"},
                    {"name": "Trim Level", "type": "STRING"},
                    {"name": "Last Mileage", "type": "INTEGER"},
                    {"name": "Web Activity", "type": "STRING"}
                ]
            },
            "data": {
                "rows": [
                    {"f": [{"v": "James Wilson"}, {"v": "(208) 228-3027"}, {"v": "james.wilson.demo@penske.com"}, {"v": "TRD Sport"}, {"v": "60334"}, {"v": "Searched TRD Off-Road suspension lift kits"}]},
                    {"f": [{"v": "Amanda Foster"}, {"v": "(385) 132-8215"}, {"v": "amanda.foster.demo@penske.com"}, {"v": "SR5"}, {"v": "52015"}, {"v": "Estimated trade-in value: $24,100 on 2021 Tacoma"}]},
                    {"f": [{"v": "Elizabeth Young"}, {"v": "(801) 502-6249"}, {"v": "elizabeth.young.demo@penske.com"}, {"v": "Limited"}, {"v": "64250"}, {"v": "Searched roof racks & towing accessories"}]},
                    {"f": [{"v": "Samantha Lewis"}, {"v": "(435) 447-6592"}, {"v": "samantha.lewis.demo@penske.com"}, {"v": "TRD Off-Road"}, {"v": "85120"}, {"v": "Estimated trade-in value: $19,500 on 2021 Tacoma"}]}
                ]
            }
        }
    else:
        table_payload = {
            "schema": {
                "fields": [
                    {"name": "Customer Name", "type": "STRING"},
                    {"name": "Vehicle Model", "type": "STRING"},
                    {"name": "Trim Level", "type": "STRING"},
                    {"name": "Active Service Visits", "type": "INTEGER"}
                ]
            },
            "data": {
                "rows": [
                    {"f": [{"v": "Michael Torres"}, {"v": "Toyota Tacoma"}, {"v": "SR (Base)"}, {"v": "1"}]},
                    {"f": [{"v": "Sarah Jenkins"}, {"v": "Toyota Tacoma"}, {"v": "SR5"}, {"v": "1"}]},
                    {"f": [{"v": "David Chen"}, {"v": "Toyota Tacoma"}, {"v": "TRD Sport"}, {"v": "1"}]}
                ]
            }
        }

    # Yield schema and data tables
    yield f"data: {json.dumps({'systemMessage': {'schema': table_payload['schema']}})}\n\n"
    time.sleep(0.2)
    yield f"data: {json.dumps({'systemMessage': {'data': table_payload['data']}})}\n\n"
    time.sleep(0.3)

    # Step E: Stream Vega-Lite Charts (Specifically for Sales Volume)
    if scenario == "sales_volume":
        vega_spec = {
            "spec": json.dumps({
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Tacoma Trim Level distribution by lease and retail purchases.",
                "width": "container",
                "height": 220,
                "data": {
                    "values": [
                        {"Trim": "SR5", "Channel": "Lease", "Units": 21},
                        {"Trim": "SR5", "Channel": "Retail", "Units": 42},
                        {"Trim": "TRD Sport", "Channel": "Lease", "Units": 15},
                        {"Trim": "TRD Sport", "Channel": "Retail", "Units": 31},
                        {"Trim": "TRD Off-Road", "Channel": "Lease", "Units": 10},
                        {"Trim": "TRD Off-Road", "Channel": "Retail", "Units": 25},
                        {"Trim": "SR (Base)", "Channel": "Lease", "Units": 8},
                        {"Trim": "SR (Base)", "Channel": "Retail", "Units": 12},
                        {"Trim": "TRD Pro", "Channel": "Lease", "Units": 3},
                        {"Trim": "TRD Pro", "Channel": "Retail", "Units": 10},
                        {"Trim": "Limited", "Channel": "Lease", "Units": 3},
                        {"Trim": "Limited", "Channel": "Retail", "Units": 5}
                    ]
                },
                "mark": "bar",
                "encoding": {
                    "y": {"field": "Trim", "type": "nominal", "sort": "-x", "title": "Trim Level"},
                    "x": {"field": "Units", "type": "quantitative", "title": "Units Sold"},
                    "color": {
                        "field": "Channel",
                        "type": "nominal",
                        "scale": {"range": ["#38bdf8", "#fbbf24"]},
                        "title": "Channel"
                    }
                },
                "config": {
                    "background": "transparent",
                    "view": {"stroke": "transparent"},
                    "axis": {
                        "grid": True,
                        "gridColor": "rgba(255,255,255,0.05)",
                        "labelColor": "#94a3b8",
                        "titleColor": "#cbd5e1"
                    },
                    "legend": {
                        "labelColor": "#94a3b8",
                        "titleColor": "#cbd5e1"
                    }
                }
            })
        }
        yield f"data: {json.dumps({'systemMessage': {'chart': vega_spec}})}\n\n"
        time.sleep(0.3)

    # Step F: Stream Custom Insights
    if scenario == "loyalty":
        insights_text = (
            "### Insights\n\n"
            "* **Flagship Retention**: Michael Torres is your highest value customer in this service cohort, recording 3 major service appointments with a total spending of $269.85.\n"
            "* **Regional Strength**: All top 5 loyal customers reside in the Idaho/Utah regional dealership zones, indicating excellent customer retention and loyalty in those dealer clusters."
        )
    elif scenario == "sales_volume":
        insights_text = (
            "### Insights\n\n"
            "* **Volume Powerhouse**: SR5 remains the dominant volume driver, representing over 35% of all active leases and retail purchases in the unified database.\n"
            "* **High-Margin Demand**: The high-margin TRD Off-Road and TRD Pro trims represent a growing segment (30% combined), indicating extremely strong customer demand for premium off-road packages."
        )
    elif scenario == "audit":
        insights_text = (
            "### Insights\n\n"
            "* **Auditing Credit Profile**: 3 out of 4 audited contracts belong to prime or subprime tiers (credit score <700), requiring extra doc verification by your billers.\n"
            "* **Toyota Financial Services**: TFS holds 50% of the audited contracts, making it the primary partner for compliance review."
        )
    elif scenario == "marketing":
        insights_text = (
            "### Insights\n\n"
            "* **Upgrade Candidate**: James Wilson is a prime candidate for an outbound TRD performance upgrade campaign, having 60k+ miles on his truck and actively searching for lift kits online.\n"
            "* **Trade-In Prospect**: Amanda Foster and Samantha Lewis are high-propensity trade-in prospects, having high-mileage Tacomas and actively running online valuation estimates."
        )
    else:
        insights_text = (
            "### Insights\n\n"
            "* **Unified Data**: Successfully unified customer records, vehicle registrations, and service records at a master record level."
        )

    yield f"data: {json.dumps({'systemMessage': {'text': {'parts': [insights_text]}}})}\n\n"
    time.sleep(0.2)

    # Step G: Stream Custom Suggestions
    if scenario == "loyalty":
        sugs = [
            "Show me the service history details for Michael Torres",
            "Predict service intervals for Utah-based Tacoma owners",
            "Generate a loyalty segment for customers with >2 service visits"
        ]
    elif scenario == "sales_volume":
        sugs = [
            "Which customers are approaching their end of lease?",
            "Compare average credit scores across different trim levels",
            "Generate a marketing campaign for TRD Pro prospects"
        ]
    elif scenario == "audit":
        sugs = [
            "Show me missing documents for Emily Rodriguez",
            "Generate an audit summary report by finance provider",
            "List all approved deals waiting for funding"
        ]
    elif scenario == "marketing":
        sugs = [
            "Generate a personalized service rate card email segment",
            "Show dealership capacity for trade-in inspections",
            "List average trade-in values for 2021 Tacomas"
        ]
    else:
        sugs = [
            "List the top 5 customers with the most service visits.",
            "Show total sales volume and lease originations by trim level.",
            "Audit the active deal jackets and list any that are currently IN_AUDIT."
        ]

    yield f"data: {json.dumps({'systemMessage': {'text': {'parts': sugs}}})}\n\n"
    yield "data: [DONE]\n\n"
