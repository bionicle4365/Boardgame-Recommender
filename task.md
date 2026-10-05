# Tasks - Milestone C1: Self-Service Cafe Onboarding & Dynamic Venue Registry

- [x] **Infrastructure & Terraform Updates**
  - [x] Define `bgg-cafes` DynamoDB table & GSI in `infrastructure/dynamodb/main.tf` and outputs in `outputs.tf` <!-- id: 0 -->
  - [x] Connect `dynamodb_cafes_table_name` through `infrastructure/main.tf` and `infrastructure/lambda/` <!-- id: 1 -->
  - [x] Add `/cafe/validate-bgg`, `/cafe/check-slug`, `/cafe/meta`, and `/cafe/onboard` routes in `infrastructure/apigateway/main.tf` <!-- id: 2 -->
  - [x] Run `terraform validate` to verify configuration syntax <!-- id: 3 -->

- [x] **Backend Handler Implementation**
  - [x] Implement `_handle_validate_bgg()` with BGG XML API2 queries, HTTP 202 retry, and shelf regex extraction <!-- id: 4 -->
  - [x] Implement `_handle_check_slug()` for slug uniqueness check <!-- id: 5 -->
  - [x] Implement `_handle_cafe_onboard()` to persist to DynamoDB, mirror to S3, and enqueue scrape job to SQS <!-- id: 6 -->
  - [x] Implement `_handle_cafe_meta()` for public cafe branding, Wi-Fi info, and table count <!-- id: 7 -->
  - [x] Integrate routing logic into `bgg_preferences/bgg_preferences_handler.py` preserving existing `/preferences` <!-- id: 8 -->

- [x] **Automated QR Generator Utility**
  - [x] Implement `scripts/generate_cafe_table_qrs.py` for print-ready table tents <!-- id: 9 -->

- [x] **Frontend Onboarding Wizard**
  - [x] Update `site_ui/assets/js/utils.js` with mock API handlers for cafe endpoints <!-- id: 10 -->
  - [x] Build glassmorphic multi-step wizard at `site_ui/cafe/onboard.html` <!-- id: 11 -->
  - [x] Embed client-side interactive table tent preview and printable card generator <!-- id: 12 -->

- [x] **Verification & Testing**
  - [x] Create unit tests in `tests/test_cafe_onboarding.py` covering all backend logic and edge cases <!-- id: 13 -->
  - [x] Run `pytest` across all tests <!-- id: 14 -->
  - [x] Test frontend locally with Jekyll and browser verification <!-- id: 15 -->
  - [x] Update `cafe_roadmap.md` on completion <!-- id: 16 -->
