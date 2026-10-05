# Implementation Plan - Milestone C1: Self-Service Cafe Onboarding & Dynamic Venue Registry

## Overview
Implement the complete self-service cafe onboarding architecture and venue registry for the Board Game Cafe & Bar Edition, enabling cafe owners to register their venue in under 3 minutes, validate their BGG collection with real-time shelf location parsing, configure table amenities, and immediately access/print table tent QR codes.

---

## 1. Architectural & Infrastructure Layer (AWS Architecture Expert)
- **DynamoDB Venue Registry (`infrastructure/dynamodb/main.tf` & `outputs.tf`)**:
  - Define `aws_dynamodb_table.bgg_cafes` (`bgg-cafes`) with:
    - Partition Key: `cafe_id` (String)
    - Global Secondary Index: `owner_cognito_id-index` on `owner_cognito_id` (String) with `projection_type = "ALL"`
    - Billing Mode: `PAY_PER_REQUEST`
  - Export `dynamodb_cafes_table_name` and `dynamodb_cafes_table_arn`.
- **Lambda Configuration Updates (`infrastructure/lambda/` & `infrastructure/main.tf`)**:
  - Update `infrastructure/main.tf` to pass `dynamodb_cafes_table_name` to `module.lambda`.
  - Update `infrastructure/lambda/variables.tf` to declare `dynamodb_cafes_table_name`.
  - Update `infrastructure/lambda/main.tf` to inject `DYNAMODB_CAFES_TABLE_NAME` and `S3_OUTPUT_BUCKET_NAME` into `bgg_preferences` Lambda environment.
- **API Gateway Routes (`infrastructure/apigateway/main.tf`)**:
  - Route `GET /cafe/validate-bgg` -> `bgg_preferences_integration` (Public)
  - Route `GET /cafe/check-slug` -> `bgg_preferences_integration` (Public)
  - Route `GET /cafe/meta` -> `bgg_preferences_integration` (Public)
  - Route `POST /cafe/onboard` -> `bgg_preferences_integration` (Cognito Authorizer)

---

## 2. Backend Schemas & Data Model (Data Expert & AWS Architecture Expert)
- **DynamoDB Record (`bgg-cafes`)**:
  - `cafe_id`: String (vanity slug)
  - `owner_cognito_id`: String
  - `name`: String
  - `bgg_username`: String
  - `slug`: String
  - `table_count`: Number
  - `wifi_ssid`: String
  - `wifi_password`: String
  - `tagline`: String
  - `shelf_regex`: String
  - `drink_pairings_enabled`: Boolean
  - `staff_pin`: String (optional)
  - `logo_url`: String (optional)
  - `created_at`: ISO timestamp
  - `updated_at`: ISO timestamp
- **S3 Cache Mirror**:
  - `s3://boardgame-app/data/cafes/{cafe_id}/meta.json`: Full cafe metadata snapshot.
  - `s3://boardgame-app/data/cafes_registry.json`: Registry map `{ cafe_id: meta }` for in-memory caching.

---

## 3. Backend Implementation (BGG API Expert & Backend Engineer)
- **`bgg_preferences/bgg_preferences_handler.py` Enhancements**:
  - Route dispatcher: inspect `rawPath` / `requestContext.http.path` and route to:
    - `/cafe/validate-bgg` -> `_handle_validate_bgg(query_params)`
    - `/cafe/check-slug` -> `_handle_check_slug(query_params)`
    - `/cafe/onboard` -> `_handle_cafe_onboard(event, body, claims)`
    - `/cafe/meta` -> `_handle_cafe_meta(query_params)`
    - default / `/preferences` -> existing `_handle_preferences()`
  - **`_handle_validate_bgg(query_params)`**:
    - Validates username.
    - Fetches user collection from BGG XML API2: `https://boardgamegeek.com/xmlapi2/collection?username={username}&own=1&stats=1&comments=1`.
    - Handles BGG 202 retry with backoff.
    - Parses XML with `xml.etree.ElementTree`.
    - Extracts `total_owned`, scans comments using `shelf_regex` (`(?:Shelf|Location|Bin):?\s*([A-Za-z0-9\-]+)` default), counts detected shelf locations, and collects up to 5 sample matches.
  - **`_handle_check_slug(query_params)`**:
    - Validates slug format.
    - Queries DynamoDB `bgg-cafes` to verify availability.
  - **`_handle_cafe_onboard(event, body, claims)`**:
    - Extracts `owner_cognito_id` from Cognito claims.
    - Validates payload: slug, name, bgg_username, table_count, wifi, etc.
    - Confirms slug availability (or ownership).
    - Persists item to `bgg-cafes` DynamoDB table.
    - Mirrors item to S3: `data/cafes/{cafe_id}/meta.json` and updates `data/cafes_registry.json`.
    - Enqueues initial scrape job to SQS `USER_SQS_QUEUE_URL`.
  - **`_handle_cafe_meta(query_params)`**:
    - Retrieves cafe metadata and returns public sanitized fields.

---

## 4. QR Generator Utility & Automated Table Tent Generation
- **`scripts/generate_cafe_table_qrs.py`**:
  - Standalone generator script producing high-resolution, print-ready SVG/HTML table tents.
  - Configurable parameters: cafe ID, name, table count range, Wi-Fi credentials, URL base.
  - Clean printable table tent layout with QR code pointing to `https://www.meeplemanifesto.com/cafe/{cafe_id}?table={table_num}`.

---

## 5. Frontend Onboarding Wizard (Site UI Expert)
- **`site_ui/cafe/onboard.html`**:
  - Responsive glassmorphic layout adhering to `site_ui/assets/css/design-system.css`.
  - Multi-step interactive wizard:
    - **Step 1: Venue & BGG Collection**: Venue name, dynamic slug validation, BGG username with live verification button, owned game counter badge, shelf tag counter, sample match preview cards, and advanced regex customization modal/expander.
    - **Step 2: Table Setup & Amenities**: Table count slider/stepper (1–100), Guest Wi-Fi SSID & Password, Custom welcome tagline, and Drink pairings toggle.
    - **Step 3: Launch & Table Tents**: Cognito authentication check, instant registration trigger, live table link, and 1-click printable table tent generation directly in-browser.
  - Support local mock API in `site_ui/assets/js/utils.js` when developing/testing locally.

---

## 6. Testing & Verification
- Unit & integration tests in `tests/test_cafe_onboarding.py`:
  - BGG validation XML parsing & retry logic.
  - Slug checking & regex extraction.
  - Cafe onboarding authorization, DynamoDB persistence, S3 mirror, SQS message dispatch.
  - Public cafe meta retrieval and sanitization.
- Run `pytest` to verify all tests pass.
- Verify frontend changes locally using Jekyll and browser subagent.
- Verify `terraform validate` passes for infrastructure changes without executing `terraform apply`.
