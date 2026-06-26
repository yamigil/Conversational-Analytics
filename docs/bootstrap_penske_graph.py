import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from google.cloud import bigquery
from google.oauth2 import service_account

# Define paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
CREDENTIALS_PATH = os.path.join(PARENT_DIR, "gilbertos-project-340619-2ed76d85322c.json")
SERVICE_CSV_PATH = os.path.join(PARENT_DIR, "Tacoma Service History with Address - file_1777923682567466.csv")

PROJECT_ID = "gilbertos-project-340619"
DATASET_ID = "penske_customer_360"
LOCATION = "us-central1"

def bootstrap_database():
    print("🚗 [1/4] Loading and parsing peer's real Toyota Tacoma service history...")
    if not os.path.exists(SERVICE_CSV_PATH):
        raise FileNotFoundError(f"Missing source CSV file at: {SERVICE_CSV_PATH}")
        
    df_raw = pd.read_csv(SERVICE_CSV_PATH)
    print(f"Loaded {len(df_raw)} raw service records.")

    # 1. Customers Table (Vertices)
    print("Parsing customers...")
    customers_data = []
    unique_names = df_raw["Name"].unique()
    for idx, name in enumerate(unique_names):
        cust_id = f"C{idx+1:03d}"
        row = df_raw[df_raw["Name"] == name].iloc[0]
        email = f"{name.lower().replace(' ', '.')}.demo@penske.com"
        customers_data.append({
            "customer_id": cust_id,
            "name": name,
            "email": email,
            "phone": row["Phone"],
            "address": row["Address"]
        })
    df_customers = pd.DataFrame(customers_data)

    # Helper to map names to customer IDs
    name_to_id = {c["name"]: c["customer_id"] for c in customers_data}

    # 2. Vehicles Table (Vertices)
    print("Parsing vehicles and assigning trim levels...")
    vehicles_data = []
    # Curated trim distribution based on sales/lease summary sheets
    trims = ["SR (Base)", "SR5", "TRD Sport", "TRD Off-Road", "TRD Pro", "Limited"]
    trim_probs = [0.15, 0.35, 0.25, 0.15, 0.05, 0.05] # SR5 & TRD Sport are flagship sellers
    purchase_types = ["RETAIL_BUY", "LEASE"]
    purchase_probs = [0.75, 0.25] # 75% buy, 25% lease

    np.random.seed(42) # Relational consistency
    unique_vins = df_raw["VIN (Synthetic)"].unique()
    
    for vin in unique_vins:
        row = df_raw[df_raw["VIN (Synthetic)"] == vin].iloc[0]
        cust_id = name_to_id[row["Name"]]
        trim = np.random.choice(trims, p=trim_probs)
        purchase_type = np.random.choice(purchase_types, p=purchase_probs)
        year = np.random.choice([2024, 2025, 2026])
        
        vehicles_data.append({
            "vin": vin,
            "customer_id": cust_id,
            "make": "Toyota",
            "model": "Tacoma",
            "trim": trim,
            "year": int(year),
            "purchase_type": purchase_type
        })
    df_vehicles = pd.DataFrame(vehicles_data)

    # 3. Service Visits Table (Vertices & Edges)
    print("Parsing service visits...")
    visits_data = []
    for idx, row in df_raw.iterrows():
        visit_id = f"V{idx+1:03d}"
        
        # Clean mileage string to integer (e.g. "15,243" -> 15243)
        mileage_str = str(row["Mileage"]).replace(",", "").strip()
        mileage = int(mileage_str) if mileage_str.isdigit() else 15000
        
        visits_data.append({
            "visit_id": visit_id,
            "vin": row["VIN (Synthetic)"],
            "service_date": row["Service Date"],
            "dealership_name": row["Dealership Name"],
            "mileage": mileage,
            "service_cost": float(row["Service Cost"]),
            "service_type": row["Service Type"]
        })
    df_service_visits = pd.DataFrame(visits_data)

    # 4. Deal Jackets Table (Vertices & Edges - F&I)
    print("Generating synthetic Deal Jackets (F&I)...")
    deals_data = []
    np.random.seed(100)
    for idx, row in df_vehicles.iterrows():
        deal_id = f"D{idx+1:03d}"
        credit_score = int(np.random.randint(580, 830))
        loan_amount = float(np.random.randint(28000, 48000))
        
        # Interest rate depends heavily on credit score
        if credit_score >= 740:
            rate = round(np.random.uniform(3.4, 4.9), 2)
        elif credit_score >= 670:
            rate = round(np.random.uniform(5.0, 6.9), 2)
        else:
            rate = round(np.random.uniform(7.0, 9.9), 2)
            
        status = np.random.choice(["APPROVED", "IN_AUDIT", "COMPLETED"], p=[0.20, 0.15, 0.65])
        
        deals_data.append({
            "deal_id": deal_id,
            "customer_id": row["customer_id"],
            "vin": row["vin"],
            "finance_provider": np.random.choice(["Toyota Financial Services", "Penske Finance", "Chase Auto", "Bank of America"]),
            "credit_score": credit_score,
            "loan_amount": loan_amount,
            "interest_rate": rate,
            "status": status
        })
    df_deal_jackets = pd.DataFrame(deals_data)

    # 5. Web Events Table (Vertices & Edges - GA4 Marketing)
    print("Generating synthetic Web Events (GA4/Marketing)...")
    events_data = []
    event_types = ["PAGE_VIEW", "TRADE_IN_ESTIMATE", "ACCESSORY_SEARCH", "BUILD_AND_PRICE"]
    np.random.seed(200)
    
    event_idx = 1
    for idx, row in df_customers.iterrows():
        cust_id = row["customer_id"]
        # Generate 1 to 3 events per customer
        num_events = np.random.randint(1, 4)
        for _ in range(num_events):
            event_id = f"E{event_idx:03d}"
            ev_type = np.random.choice(event_types)
            
            # Formulate detailed notes based on event type
            details = "Browsed new model features"
            if ev_type == "TRADE_IN_ESTIMATE":
                val = np.random.randint(18000, 32000)
                details = f"Estimated trade-in value: ${val:,} on 2021 Tacoma"
            elif ev_type == "ACCESSORY_SEARCH":
                details = np.random.choice([
                    "Searched TRD Off-Road suspension lift kits",
                    "Browsed rubber floor mats & bed liners",
                    "Searched roof racks & towing accessories"
                ])
            elif ev_type == "BUILD_AND_PRICE":
                details = "Built custom TRD Pro in Solar Octane color"
                
            # Distribute timestamps around service dates
            days_ago = np.random.randint(2, 45)
            timestamp = (datetime.now() - timedelta(days=int(days_ago))).strftime("%Y-%m-%d %H:%M:%S")
            
            events_data.append({
                "event_id": event_id,
                "customer_id": cust_id,
                "event_type": ev_type,
                "timestamp": timestamp,
                "details": details
            })
            event_idx += 1
    df_web_events = pd.DataFrame(events_data)

    # Google Cloud Authenticated Client Setup
    print("\n🔑 [2/4] Authenticating with Google Cloud BigQuery...")
    try:
        # Try to use active user session / Application Default Credentials (ADC) first
        client = bigquery.Client(project=PROJECT_ID)
        print("Using active user session / Application Default Credentials (ADC) for authentication.")
    except Exception as e:
        print(f"Active user session not active or ADC missing: {e}")
        print("Falling back to service account JSON credentials...")
        if not os.path.exists(CREDENTIALS_PATH):
            raise FileNotFoundError(f"Missing service account credentials JSON file at: {CREDENTIALS_PATH}")
        credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_PATH)
        client = bigquery.Client(credentials=credentials, project=PROJECT_ID)

    # Create Dataset if not exists
    print(f"Creating BigQuery dataset '{DATASET_ID}' (Region: {LOCATION}) if missing...")
    dataset_ref = bigquery.DatasetReference(PROJECT_ID, DATASET_ID)
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = LOCATION
    try:
        dataset = client.create_dataset(dataset)
        print(f"Dataset '{DATASET_ID}' created successfully.")
    except Exception as e:
        if "Already Exists" in str(e) or "409" in str(e):
            print(f"Dataset '{DATASET_ID}' already exists. Proceeding...")
        else:
            raise e

    # Upload Tables to BigQuery
    tables_to_upload = {
        "customers": df_customers,
        "vehicles": df_vehicles,
        "service_visits": df_service_visits,
        "deal_jackets": df_deal_jackets,
        "web_events": df_web_events
    }

    print("\n📤 [3/4] Uploading tables to BigQuery...")
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")

    for table_name, df in tables_to_upload.items():
        table_ref = dataset_ref.table(table_name)
        print(f"Uploading table '{table_name}' ({len(df)} rows)...")
        job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
        job.result() # Wait for upload to complete
        print(f"Table '{table_name}' loaded successfully.")

    # Create Property Graph Schema
    print("\n🗺️ [4/4] Creating BigQuery Property Graph Schema on top of tables...")
    
    graph_sql = f"""
    CREATE OR REPLACE PROPERTY GRAPH `{PROJECT_ID}.{DATASET_ID}.customer_360_graph`
      NODE TABLES (
        `{PROJECT_ID}.{DATASET_ID}.customers` KEY (customer_id) LABEL Customer,
        `{PROJECT_ID}.{DATASET_ID}.vehicles` KEY (vin) LABEL Vehicle,
        `{PROJECT_ID}.{DATASET_ID}.service_visits` KEY (visit_id) LABEL ServiceVisit,
        `{PROJECT_ID}.{DATASET_ID}.deal_jackets` KEY (deal_id) LABEL DealJacket,
        `{PROJECT_ID}.{DATASET_ID}.web_events` KEY (event_id) LABEL WebEvent
      )
      EDGE TABLES (
        -- Edge: Customer owns Vehicle (defined on vehicles table)
        `{PROJECT_ID}.{DATASET_ID}.vehicles` AS customer_ownership
          KEY (vin)
          SOURCE KEY (customer_id) REFERENCES `{PROJECT_ID}.{DATASET_ID}.customers` (customer_id)
          DESTINATION KEY (vin) REFERENCES `{PROJECT_ID}.{DATASET_ID}.vehicles` (vin)
          LABEL OWNS,
          
        -- Edge: Vehicle has Service Visit (defined on service_visits table)
        `{PROJECT_ID}.{DATASET_ID}.service_visits` AS vehicle_services
          KEY (visit_id)
          SOURCE KEY (vin) REFERENCES `{PROJECT_ID}.{DATASET_ID}.vehicles` (vin)
          DESTINATION KEY (visit_id) REFERENCES `{PROJECT_ID}.{DATASET_ID}.service_visits` (visit_id)
          LABEL SERVICED_AT,
          
        -- Edge: Customer has F&I Contract (defined on deal_jackets table)
        `{PROJECT_ID}.{DATASET_ID}.deal_jackets` AS customer_deals
          KEY (deal_id)
          SOURCE KEY (customer_id) REFERENCES `{PROJECT_ID}.{DATASET_ID}.customers` (customer_id)
          DESTINATION KEY (deal_id) REFERENCES `{PROJECT_ID}.{DATASET_ID}.deal_jackets` (deal_id)
          LABEL FINANCED_WITH,
          
        -- Edge: Customer triggered Web Event (defined on web_events table)
        `{PROJECT_ID}.{DATASET_ID}.web_events` AS customer_web_events
          KEY (event_id)
          SOURCE KEY (customer_id) REFERENCES `{PROJECT_ID}.{DATASET_ID}.customers` (customer_id)
          DESTINATION KEY (event_id) REFERENCES `{PROJECT_ID}.{DATASET_ID}.web_events` (event_id)
          LABEL TRIGGERED
      );
    """
    
    query_job = client.query(graph_sql)
    query_job.result() # Wait for query to complete
    print(f"🎉 BigQuery Property Graph '{DATASET_ID}.customer_360_graph' created successfully!")
    print("The customer database is fully unified and ready for AI-powered graph queries!")

if __name__ == "__main__":
    bootstrap_database()
