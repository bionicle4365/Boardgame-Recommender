# BGG Preferences & Cafe Management Lambda

A secure AWS Lambda API handler that manages user-specific settings, playgroups, and custom scoring weights in Amazon DynamoDB (`bgg-user-preferences`), as well as the complete Board Game Cafe & Bar Edition venue registry, onboarding, collection serving, and sync pipeline in DynamoDB (`bgg-cafes`) and Amazon S3.

---

## Architecture Overview

```mermaid
graph TD
    subgraph User Preferences Flow
        Client[Jekyll Web Client] -->|GET / POST /preferences + Bearer JWT| APIGW[API Gateway HTTP API]
        APIGW -->|Cognito JWT Authorizer| Lambda[BGG Preferences Lambda]
        Lambda -->|Read / Write by userId| DDBPref[(DynamoDB: bgg-user-preferences)]
    end

    subgraph Cafe Venue Management Flow
        APIGW -->|Public: /cafe/validate-bgg, /cafe/check-slug, /cafe/meta, /cafe/collection| Lambda
        APIGW -->|Auth: /cafe/onboard, /cafe/sync, /cafe/my-cafes, /cafe/update| Lambda
        Lambda -->|CRUD Venues by cafe_id| DDBCafe[(DynamoDB: bgg-cafes)]
        Lambda -->|Query Owned by owner_cognito_id| DDBCafe
        Lambda -->|Mirror Venue Metadata| S3Meta[(S3: data/cafes/{cafe_id}/meta.json)]
        Lambda -->|Serve & Prerender Collection| S3Col[(S3: data/cafes/{cafe_id}/collection.json)]
        Lambda -->|Dispatch Ingestion Scrape| SQSUser[SQS User Queue]
        EventBridge[EventBridge Weekly Trigger] -->|action: sync_all_cafes| Lambda
    end
```

---

## API Endpoints

### User Preferences Endpoints

#### 1. `GET /preferences`
- **Authentication:** Required (`Authorization: Bearer <Cognito_JWT>`).
- **Response:**
  ```json
  {
    "userId": "us-east-1:a1b2c3d4-e5f6-7890",
    "bgg_username": "boardgamer123",
    "saved_weights": {
      "w_mech": 0.60,
      "w_cat": 0.40,
      "w_pop": 0.20,
      "w_comp": 0.35,
      "w_des": 0.35,
      "w_pub": 0.10
    },
    "playgroups": [
      {
        "group_id": "grp_friday_gamers",
        "name": "Friday Game Night",
        "members": ["boardgamer123", "meeple_queen", "dice_roller"]
      }
    ]
  }
  ```

#### 2. `POST /preferences`
- **Authentication:** Required (`Authorization: Bearer <Cognito_JWT>`).
- **Payload:** Accepts updated `bgg_username`, `saved_weights`, `playgroups`, and `user_preferences`.
- **Validation:** Clamps weight values to valid numeric bounds ($0.0 - 1.0$) and triggers background user collection pre-warming via SQS.

---

### Cafe & Bar Edition Endpoints

#### 3. `GET /cafe/validate-bgg?username=XXX&shelf_regex=YYY`
- **Authentication:** Public / Anonymous.
- **Purpose:** Pre-flight onboarding check that queries BGG XML API2, counts owned games (`own=1`), and tests regex extraction of shelf location coordinates from comments.
- **Response:**
  ```json
  {
    "status": "success",
    "username": "maltandmeeple",
    "total_owned": 482,
    "shelf_tags_detected": 395,
    "sample_matches": [
      {
        "id": "13",
        "name": "Catan",
        "raw_comment": "Shelf: B-3",
        "extracted_location": "B-3"
      }
    ],
    "shelf_regex": "(?:Shelf|Location|Bin):?\\s*([A-Za-z0-9\\-]+)"
  }
  ```

#### 4. `GET /cafe/check-slug?slug=XXX`
- **Authentication:** Public / Anonymous.
- **Purpose:** Verifies whether a desired vanity slug is available in `bgg-cafes` DynamoDB.
- **Response:** `{"available": true, "slug": "the-malt-and-meeple"}`

#### 5. `POST /cafe/onboard`
- **Authentication:** Required (`Authorization: Bearer <Cognito_JWT>`).
- **Payload:**
  ```json
  {
    "cafe_id": "the-malt-and-meeple",
    "name": "The Malt & Meeple",
    "bgg_username": "maltandmeeple",
    "table_count": 25,
    "wifi_ssid": "MaltMeeple-Guest",
    "wifi_password": "rollforinitiative",
    "tagline": "Craft beer and 500+ board games on tap.",
    "shelf_regex": "(?:Shelf|Location|Bin):?\\s*([A-Za-z0-9\\-]+)",
    "drink_pairings_enabled": true
  }
  ```
- **Actions:** Persists venue record with `owner_cognito_id`, mirrors metadata to `s3://boardgame-app/data/cafes/{cafe_id}/meta.json`, updates `data/cafes_registry.json`, and dispatches initial collection scrape to `USER_SQS_QUEUE_URL`.

#### 6. `GET /cafe/meta?cafe_id=XXX`
- **Authentication:** Public / Anonymous.
- **Purpose:** Returns public branding, Wi-Fi info, table count, and tagline for patron portal header.

#### 7. `GET /cafe/collection?cafe_id=XXX`
- **Authentication:** Public / Anonymous.
- **Purpose:** Returns the cafe's library of games with physical shelf coordinates, playtimes, player counts, complexity ratings, and rules video links.
- **Performance:** Serves from pre-rendered `data/cafes/{cafe_id}/collection.json` in $<50\text{ms}$; on cold starts, loads S3 Parquet and links against master `catalog.parquet`.

#### 8. `POST /cafe/sync`
- **Authentication:** Required (`Authorization: Bearer <Cognito_JWT>`). Caller must be verified venue owner.
- **Purpose:** On-demand library re-sync. Updates `last_sync_timestamp`, purges active recommendation and collection cache keys in S3, and dispatches a fresh scrape message to SQS.

#### 9. `GET /cafe/my-cafes`
- **Authentication:** Required (`Authorization: Bearer <Cognito_JWT>`).
- **Purpose:** Queries DynamoDB `owner_cognito_id-index` GSI to return all venues owned by the caller.

#### 10. `POST /cafe/update`
- **Authentication:** Required (`Authorization: Bearer <Cognito_JWT>`). Caller must be verified venue owner.
- **Purpose:** Updates venue settings (branding, table count, Wi-Fi credentials, shelf regex) across DynamoDB and S3 metadata mirrors.

---

## Security & Multi-Tenancy

- **User Preferences:** User ID is strictly extracted from `claims['sub']`. A user can never read or overwrite another user's preferences.
- **Venue Authorization:** For `/cafe/sync` and `/cafe/update`, the handler checks that the venue's `owner_cognito_id` matches the authenticated caller's Cognito `sub`.
- **Sanitization:** Sensitive attributes like `staff_pin` are stripped from all public and owner list responses.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DYNAMODB_TABLE_NAME` | DynamoDB table name for user preferences | `bgg-user-preferences` |
| `DYNAMODB_CAFES_TABLE_NAME` | DynamoDB table name for cafe venue registry | `bgg-cafes` |
| `S3_OUTPUT_BUCKET_NAME` | S3 data lake bucket name | `boardgame-app` |
| `USER_SQS_QUEUE_URL` | SQS queue URL for collection scraping jobs | - |
| `BGG_API_TOKEN` | Optional Bearer token for BoardGameGeek API calls | - |

---

## Local Development & Testing

Run unit tests:
```bash
pytest tests/test_bgg_preferences_handler.py tests/test_cafe_onboarding.py tests/test_cafe_management.py tests/test_cafe_sync.py -v
```
