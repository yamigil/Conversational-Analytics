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
  synthetic_names AS (
    SELECT * FROM UNNEST([
      STRUCT('John' AS first_name, 'Smith' AS last_name, '(208) 555' AS phone_area, 'Idaho Falls, ID 83402' AS city_state),
      STRUCT('Jane' AS first_name, 'Doe' AS last_name, '(385) 555' AS phone_area, 'Salt Lake City, UT 84101' AS city_state),
      STRUCT('Robert' AS first_name, 'Johnson' AS last_name, '(208) 444' AS phone_area, 'Pocatello, ID 83201' AS city_state),
      STRUCT('Mary' AS first_name, 'Williams' AS last_name, '(435) 555' AS phone_area, 'St. George, UT 84770' AS city_state),
      STRUCT('James' AS first_name, 'Brown' AS last_name, '(385) 222' AS phone_area, 'Provo, UT 84601' AS city_state),
      STRUCT('Patricia' AS first_name, 'Jones' AS last_name, '(208) 333' AS phone_area, 'Twin Falls, ID 83301' AS city_state),
      STRUCT('Michael' AS first_name, 'Miller' AS last_name, '(385) 888' AS phone_area, 'Sandy, UT 84070' AS city_state),
      STRUCT('Linda' AS first_name, 'Davis' AS last_name, '(208) 777' AS phone_area, 'Boise, ID 83702' AS city_state),
      STRUCT('William' AS first_name, 'Rodriguez' AS last_name, '(435) 333' AS phone_area, 'Logan, UT 84321' AS city_state),
      STRUCT('Elizabeth' AS first_name, 'Martinez' AS last_name, '(385) 999' AS phone_area, 'Orem, UT 84057' AS city_state)
    ])
  ),
  synthetic_customers AS (
    SELECT
      CONCAT(f.first_name, ' ', l.last_name) AS name,
      FORMAT('%s-%04d', f.phone_area, ABS(MOD(FARM_FINGERPRINT(f.first_name || l.last_name), 9000)) + 1000) AS phone,
      FORMAT('%d Main St, %s', ABS(MOD(FARM_FINGERPRINT(f.first_name || l.last_name || 'addr'), 900)) + 100, f.city_state) AS address
    FROM synthetic_names f
    CROSS JOIN synthetic_names l
  ),
  combined_customers AS (
    SELECT name, phone, address FROM unique_raw_customers
    UNION DISTINCT
    SELECT name, phone, address FROM synthetic_customers
  ),
  numbered_customers AS (
    SELECT
      name,
      phone,
      address,
      ROW_NUMBER() OVER(ORDER BY name) AS row_num
    FROM combined_customers
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
  WITH real_vehicles AS (
    SELECT
      v.vin,
      c.customer_id,
      'Toyota' AS make,
      'Tacoma' AS model,
      ABS(MOD(FARM_FINGERPRINT(v.vin), 100)) AS hash_val,
      ABS(MOD(FARM_FINGERPRINT(v.vin), 3)) AS year_hash
    FROM (
      SELECT
        VIN__Synthetic_ AS vin,
        Name AS customer_name
      FROM `gilbertos-project-340619.penske_customer_360.raw_tacoma_services`
      WHERE VIN__Synthetic_ IS NOT NULL
      GROUP BY VIN__Synthetic_, Name
    ) v
    LEFT JOIN `gilbertos-project-340619.penske_customer_360.customers` c ON v.customer_name = c.name
  ),
  real_vehicles_mapped AS (
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
    FROM real_vehicles
  ),
  synthetic_customers_vehicles AS (
    SELECT
      CONCAT('5TFSYNC', customer_id, 'X01') AS vin,
      customer_id,
      'Toyota' AS make,
      CASE ABS(MOD(FARM_FINGERPRINT(customer_id), 4))
        WHEN 0 THEN 'RAV4'
        WHEN 1 THEN 'Tundra'
        WHEN 2 THEN 'Camry'
        ELSE 'Highlander'
      END AS model,
      CASE ABS(MOD(FARM_FINGERPRINT(customer_id || 'trim'), 4))
        WHEN 0 THEN 'XLE'
        WHEN 1 THEN 'Limited'
        WHEN 2 THEN 'Platinum'
        ELSE 'TRD Pro'
      END AS trim,
      2023 + ABS(MOD(FARM_FINGERPRINT(customer_id || 'year'), 3)) AS year,
      CASE WHEN MOD(ABS(FARM_FINGERPRINT(customer_id || 'pt')), 2) = 0 THEN 'RETAIL_BUY' ELSE 'LEASE' END AS purchase_type
    FROM `gilbertos-project-340619.penske_customer_360.customers`
    WHERE customer_id NOT IN (SELECT DISTINCT customer_id FROM real_vehicles_mapped)
  ),
  secondary_vehicles AS (
    SELECT
      CONCAT('5TFSYNC', customer_id, 'X02') AS vin,
      customer_id,
      'Toyota' AS make,
      CASE ABS(MOD(FARM_FINGERPRINT(customer_id || 'sec'), 4))
        WHEN 0 THEN 'Prius'
        WHEN 1 THEN 'RAV4'
        WHEN 2 THEN 'Sequoia'
        ELSE 'Camry'
      END AS model,
      CASE ABS(MOD(FARM_FINGERPRINT(customer_id || 'sectrim'), 3))
        WHEN 0 THEN 'LE'
        WHEN 1 THEN 'XLE'
        ELSE 'Limited'
      END AS trim,
      2023 + ABS(MOD(FARM_FINGERPRINT(customer_id || 'secyear'), 3)) AS year,
      CASE WHEN MOD(ABS(FARM_FINGERPRINT(customer_id || 'secpt')), 2) = 0 THEN 'RETAIL_BUY' ELSE 'LEASE' END AS purchase_type
    FROM `gilbertos-project-340619.penske_customer_360.customers`
    WHERE ABS(MOD(FARM_FINGERPRINT(customer_id), 5)) = 0
  )
  SELECT * FROM real_vehicles_mapped
  UNION ALL
  SELECT * FROM synthetic_customers_vehicles
  UNION ALL
  SELECT * FROM secondary_vehicles;
  ```

### Step 4: Cleanse & Load Service Visits (`service_visits`)
* **Task Type**: SQL Table Materialization
* **Upstream Dependency**: `create_raw_tacoma_services`
* **Query**:
  ```sql
  WITH real_visits AS (
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
  ),
  real_visits_mapped AS (
    SELECT
      FORMAT('V%03d', row_num) AS visit_id,
      vin,
      service_date,
      dealership_name,
      COALESCE(mileage, 15000) AS mileage,
      COALESCE(service_cost, 0.0) AS service_cost,
      service_type
    FROM real_visits
  ),
  synthetic_visits AS (
    SELECT
      CONCAT('V', SUBSTRING(vin, 8, 6), 'S', CAST(v_idx AS STRING)) AS visit_id,
      vin,
      DATE_SUB(CURRENT_DATE(), INTERVAL ABS(MOD(FARM_FINGERPRINT(vin || CAST(v_idx AS STRING) || 'date'), 365)) DAY) AS service_date,
      CASE ABS(MOD(FARM_FINGERPRINT(vin || CAST(v_idx AS STRING) || 'dl'), 3))
        WHEN 0 THEN 'Penske Toyota of Downey'
        WHEN 1 THEN 'Penske Toyota West'
        ELSE 'Penske Toyota of Chandler'
      END AS dealership_name,
      v_idx * 10000 + ABS(MOD(FARM_FINGERPRINT(vin || CAST(v_idx AS STRING) || 'mil'), 2500)) AS mileage,
      CASE ABS(MOD(FARM_FINGERPRINT(vin || CAST(v_idx AS STRING) || 'type'), 4))
        WHEN 0 THEN 89.95
        WHEN 1 THEN 94.50
        WHEN 2 THEN 120.00
        ELSE 145.25
      END AS service_cost,
      CASE ABS(MOD(FARM_FINGERPRINT(vin || CAST(v_idx AS STRING) || 'type'), 4))
        WHEN 0 THEN 'Full Synthetic Oil Change'
        WHEN 1 THEN 'Oil Change & Tire Rotation'
        WHEN 2 THEN 'Wheel Alignment'
        ELSE 'Transmission Service'
      END AS service_type
    FROM `gilbertos-project-340619.penske_customer_360.vehicles`,
    UNNEST([1, 2]) AS v_idx
    WHERE vin LIKE '5TFSYNC%'
  )
  SELECT * FROM real_visits_mapped
  UNION ALL
  SELECT * FROM synthetic_visits;
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
