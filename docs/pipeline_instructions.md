# BigQuery Studio Pipeline Instructions: Penske Customer 360

Use these instructions to automatically generate the visual pipeline nodes and SQL transformations for the Penske Customer 360 Property Graph pipeline.

---

## 1. Source Data Configuration
* **Source Type**: Google Cloud Storage (GCS) CSV
* **Source URI**: `gs://gilbertos-project-340619-raw/tacoma_service_history.csv`
* **Format**: CSV (skip leading row = 1, ignore unknown values)
* **Auto-Sanitized Schema**: 
  - `Name` (STRING)
  - `Service_Date` (DATE)
  - `Dealership_Name` (STRING)
  - `Mileage` (INTEGER)
  - `VIN__Synthetic_` (STRING)
  - `Service_Cost` (FLOAT)
  - `Service_Type` (STRING)
  - `Address` (STRING)
  - `Phone` (STRING)

---

## 2. Pipeline Execution Steps

### Step 1: Create Raw External Table (`create_raw_tacoma_services`)
* **Task Type**: SQL / DDL
* **Query**:
  ```sql
  CREATE OR REPLACE EXTERNAL TABLE `gilbertos-project-340619.penske_customer_360.raw_tacoma_services`
  OPTIONS (
    format = 'CSV',
    uris = ['gs://gilbertos-project-340619-raw/tacoma_service_history.csv'],
    skip_leading_rows = 1,
    allow_jagged_rows = true,
    allow_quoted_newlines = true,
    ignore_unknown_values = true
  );
  ```

### Step 2: Cleanse & Load Customers (`customers`)
* **Task Type**: SQL Table Materialization
* **Upstream Dependency**: `create_raw_tacoma_services`
* **Query**:
  ```sql
  WITH unique_raw_customers AS (
    SELECT 
      Name AS name,
      ANY_VALUE(Phone) AS phone,
      ANY_VALUE(Address) AS address
    FROM `gilbertos-project-340619.penske_customer_360.raw_tacoma_services`
    WHERE Name IS NOT NULL
    GROUP BY Name
  ),
  numbered_customers AS (
    SELECT
      name,
      phone,
      address,
      ROW_NUMBER() OVER(ORDER BY name) AS row_num
    FROM unique_raw_customers
  )
  SELECT
    FORMAT('C%03d', row_num) AS customer_id,
    name,
    LOWER(REPLACE(name, ' ', '.')) || '.demo@penske.com' AS email,
    phone,
    address
  FROM numbered_customers;
  ```

### Step 3: Cleanse & Load Vehicles (`vehicles`)
* **Task Type**: SQL Table Materialization
* **Upstream Dependency**: `customers`
* **Query**:
  ```sql
  WITH unique_raw_vehicles AS (
    SELECT
      VIN__Synthetic_ AS vin,
      Name AS customer_name
    FROM `gilbertos-project-340619.penske_customer_360.raw_tacoma_services`
    WHERE VIN__Synthetic_ IS NOT NULL
    GROUP BY VIN__Synthetic_, Name
  ),
  mapped_vehicles AS (
    SELECT
      v.vin,
      c.customer_id,
      'Toyota' AS make,
      'Tacoma' AS model,
      ABS(MOD(FARM_FINGERPRINT(v.vin), 100)) AS hash_val,
      ABS(MOD(FARM_FINGERPRINT(v.vin), 3)) AS year_hash
    FROM unique_raw_vehicles v
    LEFT JOIN `gilbertos-project-340619.penske_customer_360.customers` c ON v.customer_name = c.name
  )
  SELECT
    vin,
    customer_id,
    make,
    model,
    CASE 
      WHEN hash_val < 15 THEN 'SR (Base)'
      WHEN hash_val < 50 THEN 'SR5'
      WHEN hash_val < 75 THEN 'TRD Sport'
      WHEN hash_val < 90 THEN 'TRD Off-Road'
      WHEN hash_val < 95 THEN 'TRD Pro'
      ELSE 'Limited'
    END AS trim,
    CASE year_hash
      WHEN 0 THEN 2024
      WHEN 1 THEN 2025
      ELSE 2026
    END AS year,
    CASE 
      WHEN hash_val < 75 THEN 'RETAIL_BUY'
      ELSE 'LEASE'
    END AS purchase_type
  FROM mapped_vehicles;
  ```

### Step 4: Cleanse & Load Service Visits (`service_visits`)
* **Task Type**: SQL Table Materialization
* **Upstream Dependency**: `create_raw_tacoma_services`
* **Query**:
  ```sql
  WITH cleaned_visits AS (
    SELECT
      VIN__Synthetic_ AS vin,
      Service_Date AS service_date,
      Dealership_Name AS dealership_name,
      Mileage AS mileage,
      Service_Cost AS service_cost,
      Service_Type AS service_type,
      ROW_NUMBER() OVER(ORDER BY Service_Date, VIN__Synthetic_) AS row_num
    FROM `gilbertos-project-340619.penske_customer_360.raw_tacoma_services`
    WHERE VIN__Synthetic_ IS NOT NULL
  )
  SELECT
    FORMAT('V%03d', row_num) AS visit_id,
    vin,
    service_date,
    dealership_name,
    COALESCE(mileage, 15000) AS mileage,
    COALESCE(service_cost, 0.0) AS service_cost,
    service_type
  FROM cleaned_visits;
  ```

### Step 5: Synthesize Deal Jackets (`deal_jackets`)
* **Task Type**: SQL Table Materialization
* **Upstream Dependency**: `vehicles`
* **Query**:
  ```sql
  WITH base_deals AS (
    SELECT
      vin,
      customer_id,
      ROW_NUMBER() OVER(ORDER BY vin) AS row_num,
      580 + ABS(MOD(FARM_FINGERPRINT(vin), 250)) AS credit_score,
      28000 + ABS(MOD(FARM_FINGERPRINT(vin || 'loan'), 20000)) AS loan_amount,
      ABS(MOD(FARM_FINGERPRINT(vin || 'provider'), 4)) AS provider_hash,
      ABS(MOD(FARM_FINGERPRINT(vin || 'status'), 100)) AS status_hash
    FROM `gilbertos-project-340619.penske_customer_360.vehicles`
  )
  SELECT
    FORMAT('D%03d', row_num) AS deal_id,
    customer_id,
    vin,
    CASE provider_hash
      WHEN 0 THEN 'Toyota Financial Services'
      WHEN 1 THEN 'Penske Finance'
      WHEN 2 THEN 'Chase Auto'
      ELSE 'Bank of America'
    END AS finance_provider,
    credit_score,
    CAST(loan_amount AS FLOAT64) AS loan_amount,
    CASE 
      WHEN credit_score >= 740 THEN ROUND(3.4 + ABS(MOD(FARM_FINGERPRINT(vin || 'rate'), 150)) / 100.0, 2)
      WHEN credit_score >= 670 THEN ROUND(5.0 + ABS(MOD(FARM_FINGERPRINT(vin || 'rate'), 190)) / 100.0, 2)
      ELSE ROUND(7.0 + ABS(MOD(FARM_FINGERPRINT(vin || 'rate'), 290)) / 100.0, 2)
    END AS interest_rate,
    CASE 
      WHEN status_hash < 20 THEN 'APPROVED'
      WHEN status_hash < 35 THEN 'IN_AUDIT'
      ELSE 'COMPLETED'
    END AS status
  FROM base_deals;
  ```

### Step 6: Synthesize GA4 Web Events (`web_events`)
* **Task Type**: SQL Table Materialization
* **Upstream Dependency**: `customers`
* **Query**:
  ```sql
  WITH exploded_customers AS (
    SELECT
      customer_id,
      idx,
      ABS(MOD(FARM_FINGERPRINT(customer_id || CAST(idx AS STRING)), 4)) AS type_hash,
      ABS(MOD(FARM_FINGERPRINT(customer_id || CAST(idx AS STRING) || 'days'), 43)) + 2 AS days_ago,
      ABS(MOD(FARM_FINGERPRINT(customer_id || CAST(idx AS STRING) || 'trade'), 14000)) + 18000 AS trade_val,
      ABS(MOD(FARM_FINGERPRINT(customer_id || CAST(idx AS STRING) || 'acc'), 3)) AS acc_hash
    FROM `gilbertos-project-340619.penske_customer_360.customers`,
    UNNEST([1, 2]) AS idx
  ),
  numbered_events AS (
    SELECT
      customer_id,
      CASE type_hash
        WHEN 0 THEN 'PAGE_VIEW'
        WHEN 1 THEN 'TRADE_IN_ESTIMATE'
        WHEN 2 THEN 'ACCESSORY_SEARCH'
        ELSE 'BUILD_AND_PRICE'
      END AS event_type,
      TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL days_ago DAY) AS event_timestamp,
      CASE type_hash
        WHEN 1 THEN 'Estimated trade-in value: $' || FORMAT("%'d", trade_val) || ' on 2021 Tacoma'
        WHEN 2 THEN 
          CASE acc_hash
            WHEN 0 THEN 'Searched TRD Off-Road suspension lift kits'
            WHEN 1 THEN 'Browsed rubber floor mats & bed liners'
            ELSE 'Searched roof racks & towing accessories'
          END
        WHEN 3 THEN 'Built custom TRD Pro in Solar Octane color'
        ELSE 'Browsed new model features'
      END AS details,
      ROW_NUMBER() OVER(ORDER BY customer_id, idx) AS row_num
    FROM exploded_customers
  )
  SELECT
    FORMAT('E%03d', row_num) AS event_id,
    customer_id,
    event_type,
    FORMAT_TIMESTAMP("%Y-%m-%d %H:%M:%S", event_timestamp) AS timestamp,
    details
  FROM numbered_events;
  ```

### Step 7: Build Property Graph (`customer_360_graph`)
* **Task Type**: SQL / DDL Execution
* **Upstream Dependencies**: `customers`, `vehicles`, `service_visits`, `deal_jackets`, `web_events`
* **Query**:
  ```sql
  CREATE OR REPLACE PROPERTY GRAPH `gilbertos-project-340619.penske_customer_360.customer_360_graph`
    NODE TABLES (
      `gilbertos-project-340619.penske_customer_360.customers` KEY (customer_id) LABEL Customer,
      `gilbertos-project-340619.penske_customer_360.vehicles` KEY (vin) LABEL Vehicle,
      `gilbertos-project-340619.penske_customer_360.service_visits` KEY (visit_id) LABEL ServiceVisit,
      `gilbertos-project-340619.penske_customer_360.deal_jackets` KEY (deal_id) LABEL DealJacket,
      `gilbertos-project-340619.penske_customer_360.web_events` KEY (event_id) LABEL WebEvent
    )
    EDGE TABLES (
      `gilbertos-project-340619.penske_customer_360.vehicles` AS customer_ownership
        KEY (vin)
        SOURCE KEY (customer_id) REFERENCES `gilbertos-project-340619.penske_customer_360.customers` (customer_id)
        DESTINATION KEY (vin) REFERENCES `gilbertos-project-340619.penske_customer_360.vehicles` (vin)
        LABEL OWNS,
      `gilbertos-project-340619.penske_customer_360.service_visits` AS vehicle_services
        KEY (visit_id)
        SOURCE KEY (vin) REFERENCES `gilbertos-project-340619.penske_customer_360.vehicles` (vin)
        DESTINATION KEY (visit_id) REFERENCES `gilbertos-project-340619.penske_customer_360.service_visits` (visit_id)
        LABEL SERVICED_AT,
      `gilbertos-project-340619.penske_customer_360.deal_jackets` AS customer_deals
        KEY (deal_id)
        SOURCE KEY (customer_id) REFERENCES `gilbertos-project-340619.penske_customer_360.customers` (customer_id)
        DESTINATION KEY (deal_id) REFERENCES `gilbertos-project-340619.penske_customer_360.deal_jackets` (deal_id)
        LABEL FINANCED_WITH,
      `gilbertos-project-340619.penske_customer_360.web_events` AS customer_web_events
        KEY (event_id)
        SOURCE KEY (customer_id) REFERENCES `gilbertos-project-340619.penske_customer_360.customers` (customer_id)
        DESTINATION KEY (event_id) REFERENCES `gilbertos-project-340619.penske_customer_360.web_events` (event_id)
        LABEL TRIGGERED
    );
  ```
