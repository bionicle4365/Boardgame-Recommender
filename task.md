# Tasks - Milestone C2: Cafe Inventory Ingestion & On-Demand Sync

- [x] **Data Pipeline & Scraper Updates**
  - [x] Update [`bgg_user_data_scraper`](file:///d:/Git/Boardgame-Recommender/bgg_user_data_scraper) to process `is_cafe=true` in SQS messages <!-- id: 0 -->
  - [x] Filter BGG collection strictly for `own=1` and write Parquet to `s3://boardgame-app/data/cafes/{cafe_id}/collection.parquet` <!-- id: 1 -->

- [x] **On-Demand Sync Endpoint**
  - [x] Implement `_handle_cafe_sync()` in [`bgg_preferences_handler.py`](file:///d:/Git/Boardgame-Recommender/bgg_preferences/bgg_preferences_handler.py) <!-- id: 2 -->
  - [x] Validate caller ownership in `bgg-cafes` DynamoDB table <!-- id: 3 -->
  - [x] Enqueue scrape job with `{ "username": bgg_username, "cafe_id": cafe_id, "is_cafe": true }` to `USER_SQS_QUEUE_URL` <!-- id: 4 -->
  - [x] Clear cafe recommendation cache keys <!-- id: 5 -->

- [x] **API Gateway & EventBridge Infrastructure**
  - [x] Add `POST /cafe/sync` route with Cognito authorizer in [`infrastructure/apigateway/main.tf`](file:///d:/Git/Boardgame-Recommender/infrastructure/apigateway/main.tf) <!-- id: 6 -->
  - [x] Define weekly EventBridge trigger for recurring cafe collection sync <!-- id: 7 -->

- [x] **Verification & Testing**
  - [x] Add unit tests in `tests/test_cafe_sync.py` or `tests/test_bgg_preferences_handler.py` covering sync handler and authorization <!-- id: 8 -->
  - [x] Test scraper cafe parquet extraction logic with mock BGG XML payload <!-- id: 9 -->
  - [x] Update `cafe_roadmap.md` on completion <!-- id: 10 -->
