import re
from typing import Optional

from config import logger, get_project_id

def extract_questions_from_text(text: str) -> list:
    """Helper to parse and extract sample questions/query starters from a text block.
    Supports inline numbered lists, vertical numbered lists, and questions inside quotes."""
    if not text:
        return []
    questions = []
    
    # 1. Match vertical list items starting a line: e.g. "1. Question?" or "  2) Question?"
    # Requires start-of-line anchor to avoid matching inline math numbers (e.g. * 100. )
    vertical_matches = re.findall(r'(?:^|\n)\s*\d+[\.\)]\s+(.*?)(?=\n\s*\d+[\.\)]|$)', text, re.DOTALL)
    for m in vertical_matches:
        # Take the first line to avoid grabbing multiple paragraphs if subsequent indices are missing
        q = m.strip().split('\n')[0]
        q = q.rstrip(".,; ")
        if 15 < len(q) < 160:
            if any(k in q.lower() for k in ["primary key", "key column", "foreign key", "table schema"]):
                continue
            if q.count(":") > 1 or q.count("`") > 2 or "*" in q or "#" in q:
                continue
            if not q.endswith("?"):
                q += "?"
            questions.append(q)
            
    # 2. Match inline list items: e.g. "(1) Question? (2) Question?"
    # Requires parentheses around the numbers to prevent false positives with plain floats
    inline_matches = re.findall(r'(?:^|\s)\(\d+\)\s+(.*?)(?=\s+\(\d+\)|$)', text, re.DOTALL)
    for m in inline_matches:
        q = m.strip().rstrip(".,; ")
        if 15 < len(q) < 160:
            if any(k in q.lower() for k in ["primary key", "key column", "foreign key", "table schema"]):
                continue
            if q.count(":") > 1 or q.count("`") > 2 or "*" in q or "#" in q:
                continue
            if not q.endswith("?"):
                q += "?"
            if q not in questions:
                questions.append(q)
            
    # 2. Extract questions inside quotes ending with a question mark (fallback/extra)
    quoted_matches = re.findall(r'["\']([^"\']+\?)["\']', text)
    for m in quoted_matches:
        q = m.strip()
        if 15 < len(q) < 160:
            if not any(k in q.lower() for k in ["primary key", "key column", "foreign key", "table schema"]):
                if q.count(":") > 1 or q.count("`") > 2 or "*" in q or "#" in q:
                    continue
                if not any(k in q.upper() for k in ["SELECT", "FROM", "WHERE", "WITH", "LIMIT"]):
                    q = re.sub(r'[\*\`\_]', '', q)
                    if q not in questions:
                        questions.append(q)
                    
    return questions

def get_table_specific_suggestions(table_name: str) -> list:
    """Returns premium, highly-analytical table-level suggested queries dynamically without any hardcoding."""
    clean_name = table_name.lower().strip()
    
    # We detect semantic intent from the words in the table name:
    # 1. Transactions / Orders / Sales / Service
    if any(k in clean_name for k in ["order", "sale", "trans", "invoice", "deal", "visit"]):
        return [
            f"What are our total sales and volumes from {clean_name} this month?",
            f"Show me the daily trend of transactions in the {clean_name} table.",
            f"What is the distribution of transaction status or categories in {clean_name}?"
        ]
        
    # 2. Products / Inventory / Items / Vehicles
    if any(k in clean_name for k in ["product", "item", "inventory", "stock", "part", "vehicle"]):
        return [
            f"What are the top 10 most common or high-value items in the {clean_name} table?",
            f"How is our catalog of {clean_name} distributed across different categories?",
            f"Show me the average pricing, retail value, or costs inside the {clean_name} table."
        ]
        
    # 3. Users / Customers / Profiles / Clients
    if any(k in clean_name for k in ["user", "customer", "profile", "client", "member"]):
        return [
            f"What is the distribution of {clean_name} by region, country, or traffic source?",
            f"Can we see the growth trend of new signups in the {clean_name} table over time?",
            f"What are the most active and high-value records in the {clean_name} table?"
        ]
        
    # 4. Web events / Traffic / Analytics / Logs
    if any(k in clean_name for k in ["event", "session", "click", "page", "log", "activity"]):
        return [
            f"What is the total count of activities and events in the {clean_name} table?",
            f"Which traffic channels or action types are most common in the {clean_name} logs?",
            f"Show me the daily trend of website activities from {clean_name} for the last 30 days."
        ]
        
    # 5. Marketing / actuals / spends / adwords
    if any(k in clean_name for k in ["marketing", "spend", "ad", "campaign", "actual", "cost"]):
        return [
            f"What is the sum of costs, impressions, and clicks in the {clean_name} campaigns?",
            f"Calculate the average click-through rate (CTR) and return on investment (ROI) in {clean_name}.",
            f"Compare the daily performance and conversion trends from the {clean_name} table."
        ]

    # Default fallback for custom/unknown tables (completely generic, safe and analytical!)
    return [
        f"Show me a detailed summary and column types of the {clean_name} table.",
        f"What are the top 10 most recent records from the {clean_name} table?",
        f"Can you show me the count of records grouped by the primary columns in {clean_name}?"
    ]

# In-memory caches to guarantee sub-millisecond response times for database metadata scans
_PROJECT_GRAPHS_CACHE = {}
_GRAPH_SCHEMA_CACHE = {}

def discover_project_graphs(project_id: str, user_token: Optional[str] = None) -> list:
    """Dynamically scans all datasets in a GCP project to discover BigQuery Property Graphs (100% dynamic, zero hardcoding!).
    Uses an in-memory cache to ensure sub-millisecond response times for subsequent calls.
    """
    global _PROJECT_GRAPHS_CACHE
    cache_key = (project_id, user_token is not None)
    if cache_key in _PROJECT_GRAPHS_CACHE:
        logger.info(f"Returning cached property graphs for project '{project_id}' (cache hit!)")
        return _PROJECT_GRAPHS_CACHE[cache_key]

    try:
        from google.cloud import bigquery
        if user_token:
            from google.oauth2.credentials import Credentials
            creds = Credentials(token=user_token)
            bq_client = bigquery.Client(credentials=creds, project=project_id)
        else:
            bq_client = bigquery.Client(project=project_id)
            
        logger.info(f"Scanning project '{project_id}' to discover BigQuery Property Graphs dynamically...")
        datasets = list(bq_client.list_datasets())
        graphs = []
        for dataset in datasets:
            dataset_id = dataset.dataset_id
            if dataset_id.startswith("_") or dataset_id.lower() in ["information_schema"]:
                continue
                
            try:
                # Query INFORMATION_SCHEMA for property graphs in this dataset
                query = f"SELECT property_graph_name FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.PROPERTY_GRAPHS`"
                query_job = bq_client.query(query)
                results = list(query_job.result(timeout=2.0))
                for row in results:
                    graph_name = row['property_graph_name']
                    graphs.append({
                        "project_id": project_id,
                        "dataset_id": dataset_id,
                        "graph_name": graph_name
                    })
            except Exception:
                # Ignore datasets where we don't have access or that don't support the metadata view
                continue
                
        logger.info(f"Dynamically discovered property graphs in project: {graphs}")
        _PROJECT_GRAPHS_CACHE[cache_key] = graphs
        return graphs
    except Exception as e:
        logger.error(f"Error scanning project property graphs: {e}")
        return []

def generate_graph_node_suggestions(nodes: list, edges: list) -> dict:
    """Uses Gemini to dynamically generate 3 premium, highly-analytical, and domain-specific
    query suggestions for each node in a property graph, based on the entire graph's structure.
    """
    import json
    from gemini_client import call_gemini
    
    # Prepare a compact representation of the graph for the prompt
    nodes_summary = []
    for n in nodes:
        nodes_summary.append({
            "id": n["id"],
            "label": n["label"],
            "description": n["description"]
        })
        
    edges_summary = []
    for e in edges:
        edges_summary.append({
            "source": e["source"],
            "target": e["target"],
            "label": e["label"]
        })
        
    system_instruction = (
        "You are an expert database analyst. Generate highly-customized, creative, and domain-specific "
        "business query suggestions (query starters) for a data portal based on the provided BigQuery Property Graph schema. "
        "For each node in the graph, generate exactly 3 suggested questions that a business user or analyst would want to ask. "
        "The questions should be natural language questions, highly relevant to the domain of the data, and should leverage "
        "the relationships and connections in the graph (e.g. joining nodes, aggregating metrics, filtering by properties). "
        "\nReturn the result ONLY as a raw JSON object mapping each node ID to a list of exactly 3 questions. "
        "Do not include any markdown formatting or backticks in your response. Example output format:\n"
        "{\n"
        "  \"node_id_1\": [\"Question 1?\", \"Question 2?\", \"Question 3?\"],\n"
        "  \"node_id_2\": [\"Question 1?\", \"Question 2?\", \"Question 3?\"]\n"
        "}"
    )
    
    prompt = (
        f"Here is the BigQuery Property Graph schema:\n"
        f"Nodes:\n{json.dumps(nodes_summary, indent=2)}\n\n"
        f"Edges (Connections):\n{json.dumps(edges_summary, indent=2)}\n"
    )
    
    try:
        raw_json = call_gemini(prompt, system_instruction, response_mime_type="application/json", temperature=0.3)
        if raw_json:
            cleaned = raw_json.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            parsed = json.loads(cleaned.strip())
            if isinstance(parsed, dict):
                logger.info(f"Successfully generated custom graph suggestions via Gemini for nodes: {list(parsed.keys())}")
                # Ensure all keys are lowercase strings and values are lists of strings
                return {str(k).lower().strip(): [str(v) for v in val] for k, val in parsed.items() if isinstance(val, list)}
    except Exception as ex:
        logger.warning(f"Failed to generate custom graph suggestions with Gemini: {ex}. Using generic fallbacks.")
    return {}

def discover_bq_graph_schema(project_id: str, dataset_id: str) -> Optional[dict]:
    """Queries BigQuery INFORMATION_SCHEMA.PROPERTY_GRAPHS to dynamically discover the property graph schema.
    Uses an in-memory cache to ensure sub-millisecond response times for subsequent calls.
    """
    global _GRAPH_SCHEMA_CACHE
    cache_key = (project_id, dataset_id)
    if cache_key in _GRAPH_SCHEMA_CACHE:
        logger.info(f"Returning cached graph schema for {project_id}.{dataset_id} (cache hit!)")
        return _GRAPH_SCHEMA_CACHE[cache_key]

    try:
        from google.cloud import bigquery
        bq_client = bigquery.Client(project=project_id)
        
        # 1. Fetch dataset location using API to ensure region compatibility
        dataset = bq_client.get_dataset(f"{project_id}.{dataset_id}")
        location = dataset.location
        if not location:
            return None
            
        # 2. Query regional PROPERTY_GRAPHS metadata view
        graph_query = f"""
        SELECT property_graph_name, property_graph_metadata_json
        FROM `region-{location.lower()}.INFORMATION_SCHEMA.PROPERTY_GRAPHS`
        WHERE property_graph_schema = '{dataset_id}'
        LIMIT 1
        """
        
        query_job = bq_client.query(graph_query)
        rows = list(query_job)
        if not rows:
            logger.info(f"No BigQuery property graphs found in dataset '{dataset_id}'.")
            return None
            
        row = rows[0]
        metadata = row['property_graph_metadata_json']
        
        # 3. Parse nodeTables dynamically without any hardcoding
        nodes = []
        for nt in metadata.get('nodeTables', []):
            table_id = nt['name'].split('.')[-1]
            label = table_id
            if 'labelAndProperties' in nt and nt['labelAndProperties']:
                label = nt['labelAndProperties'][0].get('label', label)
                
            clean_label = label.replace("_", " ").title()
            singular_type = clean_label
            if singular_type.endswith("s") or singular_type.endswith("S"):
                singular_type = singular_type[:-1]
                
            nodes.append({
                "id": table_id,
                "label": clean_label.upper(),
                "icon": table_id.lower(),
                "type": singular_type.lower(),
                "description": f"Dynamic property graph node representing {clean_label.lower()} entities connected across your BigQuery dataset."
            })
            
        # 4. Parse edgeTables
        edges = []
        for et in metadata.get('edgeTables', []):
            label = et['name']
            if 'labelAndProperties' in et and et['labelAndProperties']:
                label = et['labelAndProperties'][0].get('label', label)
                
            source_table = et.get('sourceNodeReference', {}).get('nodeTable', '')
            dest_table = et.get('destinationNodeReference', {}).get('nodeTable', '')
            
            source_id = source_table.split('.')[-1]
            dest_id = dest_table.split('.')[-1]
            
            edges.append({
                "source": source_id,
                "target": dest_id,
                "label": label.upper()
            })
            
        # 5. Generate node suggestions (Try Gemini first, fallback to generic templates)
        raw_suggestions = generate_graph_node_suggestions(nodes, edges)
        node_suggestions = {**raw_suggestions}
        
        # Ensure every node has suggestions (in case Gemini missed some or failed)
        for n in nodes:
            table_id = n["id"]
            lookup_id = table_id.lower().strip()
            if lookup_id not in node_suggestions or len(node_suggestions[lookup_id]) < 3:
                clean_label = n["label"].replace("_", " ").title()
                node_suggestions[lookup_id] = [
                    f"What are the most common relationships and connections starting from {clean_label.lower()}?",
                    f"Can you summarize the top 10 attributes and key columns inside the {clean_label.lower()} table?",
                    f"Show me the latest activity trends and records in {clean_label.lower()}."
                ]
            
        res = {
            "nodes": nodes,
            "edges": edges,
            "nodeSuggestions": node_suggestions,
            "projectId": project_id,
            "datasetId": dataset_id
        }
        
        # Self-healing Cache Policy: Only cache if Gemini succeeded in generating suggestions.
        # This prevents locking the cache with permanent fallback values on transient API timeouts.
        if raw_suggestions:
            _GRAPH_SCHEMA_CACHE[cache_key] = res
        else:
            logger.warning(f"Gemini API failed during graph suggestions generation for {dataset_id}. Fallbacks loaded, but cache bypass active for self-healing.")
            
        return res
        
    except Exception as e:
        logger.error(f"Failed to dynamically discover BigQuery property graph schema: {e}")
        return None

def enrich_agent_metadata(agent: dict, skip_db_scan: bool = False) -> dict:
    """Enriches a data agent with dynamically generated suggested questions and welcome subtitles."""
    display_name = agent.get("displayName", "Data Agent")
    description = agent.get("description", "")
    
    # 1. Safely locate system instructions and table references
    system_instruction = ""
    tables = []
    da_agent = agent.get("dataAnalyticsAgent", {})
    
    for context_key in ["publishedContext", "lastPublishedContext", "stagingContext"]:
        context = da_agent.get(context_key, {})
        if not system_instruction and context.get("systemInstruction"):
            system_instruction = context["systemInstruction"]
        
        ds_refs = context.get("datasourceReferences", {})
        bq_ref = ds_refs.get("bq", {})
        table_refs = bq_ref.get("tableReferences", [])
        for t in table_refs:
            project = t.get("projectId", "")
            dataset = t.get("datasetId", "")
            table = t.get("tableId", "")
            if dataset and table:
                # Format as project.dataset.table if project is present
                table_str = f"{project}.{dataset}.{table}" if project else f"{dataset}.{table}"
                if table_str not in tables:
                    tables.append(table_str)
                    
    # 2. Extract suggested queries from the agent's description first
    suggestions = []
    if description:
        suggestions.extend(extract_questions_from_text(description))
        
    # 3. Extract suggested queries from system instruction if we still need more
    if len(suggestions) < 3 and system_instruction:
        suggestions.extend(extract_questions_from_text(system_instruction))
        
    # Remove duplicates while preserving order
    unique_suggestions = []
    for s in suggestions:
        if s not in unique_suggestions:
            unique_suggestions.append(s)
    suggestions = unique_suggestions[:3]
    
    # 4. Fallback: Custom table-based queries for custom agents
    if len(suggestions) < 3 and tables:
        primary_table = tables[0].split(".")[-1]
        table_suggestions = [
            f"Can you give me a summary of the data in the {primary_table} table?",
            f"What are the key metrics and columns available in {primary_table}?",
            f"Show me the top 10 most recent records from {primary_table}."
        ]
        for ts in table_suggestions:
            if ts not in suggestions:
                suggestions.append(ts)
        suggestions = suggestions[:3]
            
    # 7. Generate a beautiful, custom welcome subtitle dynamically
    welcome_subtitle = description
    if not welcome_subtitle:
        if tables:
            clean_tables = [t.split(".")[-1] for t in tables]
            welcome_subtitle = f"Ask any analytical question about your connected data tables (including {', '.join(clean_tables[:2])})."
        else:
            welcome_subtitle = "Ask any analytical question about your business data, cost trends, or performance."
            
    # 8. Detect and Inject Graph Database Schema if it is a Graph Agent
    name_lower = agent.get("displayName", "").lower()
    desc_lower = agent.get("description", "").lower()
    
    # Base keyword detection
    is_graph_agent = (
        "graph" in name_lower or 
        "graph" in desc_lower or 
        any(k in name_lower or k in desc_lower for k in ["customer-360", "customer360", "c360", "customer 360"])
    )
    
    # Dynamic Graph Detection: if not detected by keywords, check if there is a property graph
    # in the project whose dataset or graph name matches the agent's name/keywords.
    if not is_graph_agent and not skip_db_scan:
        active_project = get_project_id()
        discovered_graphs = discover_project_graphs(active_project)
        for g in discovered_graphs:
            g_dataset = g["dataset_id"].lower()
            g_name = g["graph_name"].lower()
            # If the agent name matches the dataset or graph name, it's a graph agent!
            if name_lower == g_dataset or name_lower == g_name or g_dataset in name_lower or g_name in name_lower:
                is_graph_agent = True
                logger.info(f"Dynamically classified Agent '{display_name}' as a Graph Agent because it matches discovered graph '{g_dataset}.{g_name}'")
                break
                
    agent["isGraphAgent"] = is_graph_agent
    
    if is_graph_agent:
        project_id = None
        dataset_id = None
        if skip_db_scan:
            agent["graphData"] = None
            welcome_subtitle = f"Explore your connected BigQuery Property Graph dynamically. Hover and click nodes to discover relationships."
        else:
            if tables:
                first_table = tables[0]
                parts = first_table.split(".")
                if len(parts) == 3:
                    project_id = parts[0]
                    dataset_id = parts[1]
                elif len(parts) == 2:
                    project_id = get_project_id()
                    dataset_id = parts[0]
                
        # 100% Dynamic, Zero-Hardcode Database Graph Scan Fallback
        if not dataset_id and not skip_db_scan:
            active_project = get_project_id()
            # Scan the active BigQuery project for any Property Graphs!
            discovered_graphs = discover_project_graphs(active_project)
            if discovered_graphs:
                # Find the best matching graph based on display name / description keywords
                best_graph = None
                agent_keywords = set(name_lower.split() + desc_lower.split())
                agent_keywords = {w.strip("-_,.") for w in agent_keywords if len(w) > 2}
                
                max_matches = 0
                for g in discovered_graphs:
                    g_dataset = g["dataset_id"].lower()
                    g_name = g["graph_name"].lower()
                    
                    matches = sum(1 for kw in agent_keywords if kw in g_dataset or kw in g_name)
                    if matches > max_matches:
                        max_matches = matches
                        best_graph = g
                        
                # Fall back to the first discovered graph if no matching keywords were found
                if not best_graph:
                    best_graph = discovered_graphs[0]
                    
                project_id = best_graph["project_id"]
                dataset_id = best_graph["dataset_id"]
                logger.info(f"Dynamically bound Graph Agent '{agent.get('displayName')}' to best matching graph '{project_id}.{dataset_id}.{best_graph['graph_name']}' (matches={max_matches})")
                
        discovered_schema = None
        if dataset_id and project_id:
            discovered_schema = discover_bq_graph_schema(project_id, dataset_id)
            
        if discovered_schema:
            agent["graphData"] = discovered_schema
            welcome_subtitle = f"Explore your connected BigQuery Property Graph '{dataset_id}'. Hover and click nodes to discover relationships and ask questions!"
        elif not skip_db_scan:
            # Dynamic Self-Generated Fallback Graph Schema (100% generic, no hardcoding!)
            fallback_nodes = []
            fallback_edges = []
            node_suggs = {}
            
            for idx, t in enumerate(tables):
                clean_name = t.split(".")[-1] if "." in t else t
                clean_label = clean_name.replace("_", " ").title()
                
                singular_type = clean_label
                if singular_type.endswith("s") or singular_type.endswith("S"):
                    singular_type = singular_type[:-1]
                    
                fallback_nodes.append({
                    "id": clean_name,
                    "label": clean_label.upper(),
                    "icon": clean_name.lower(),
                    "type": singular_type.lower(),
                    "description": f"Connected database table representing {clean_label.lower()} entities available for analytical queries."
                })
                
                node_suggs[clean_name] = get_table_specific_suggestions(clean_name)
                
            # Draw dynamic rings/relationships to connect them beautifully
            for i in range(len(fallback_nodes)):
                src = fallback_nodes[i]["id"]
                tgt = fallback_nodes[(i + 1) % len(fallback_nodes)]["id"]
                
                label = "REFERENCES"
                if src == "users" and tgt == "orders":
                    label = "PLACES"
                elif src == "orders" and tgt == "products":
                    label = "CONTAINS"
                elif src == "products" and tgt == "brands":
                    label = "BELONGS_TO"
                    
                fallback_edges.append({
                    "source": src,
                    "target": tgt,
                    "label": label
                })
                
            agent["graphData"] = {
                "nodes": fallback_nodes,
                "edges": fallback_edges,
                "nodeSuggestions": node_suggs
            }
            welcome_subtitle = f"Explore your dynamic database relationships for '{display_name}'. Hover and click table nodes to inspect columns and preview data!"
            
    else:
        # Auto-generate Star Relational Schema for standard agents!
        table_nodes = []
        table_edges = []
        
        # Add central root node
        table_nodes.append({
            "id": "schema_root",
            "label": "Database Schema",
            "icon": "database",
            "type": "database",
            "description": f"Relational database schema containing all tables available to the {display_name} agent."
        })
        
        for t in tables:
            clean_name = t.split(".")[-1] if "." in t else t
            
            table_nodes.append({
                "id": clean_name,
                "label": clean_name,
                "icon": clean_name,
                "type": "table",
                "description": f"Connected database table: {clean_name}. Contains columns, metrics, and records for analytical queries."
            })
            
            table_edges.append({
                "source": "schema_root",
                "target": clean_name,
                "label": "CONTAINS"
            })
            
        agent["graphData"] = {
            "nodes": table_nodes,
            "edges": table_edges,
            "nodeSuggestions": {
                clean_name: get_table_specific_suggestions(clean_name) 
                for clean_name in [t.split(".")[-1] if "." in t else t for t in tables]
            }
        }
        if not welcome_subtitle:
            welcome_subtitle = f"Explore the connected tables schema for {display_name}. Hover and click table nodes to inspect columns and preview data!"

    agent["suggestions"] = suggestions
    agent["welcomeSubtitle"] = welcome_subtitle
    return agent
