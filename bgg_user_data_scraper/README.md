# BGG User Data Scraper Lambda (`bgg_user_data_scraper`)

An SQS-triggered containerized AWS Lambda worker that downloads collection and ownership data from the BoardGameGeek XML API2, supporting both individual user taste profiles and commercial cafe venue inventories.

---

## Operating Modes

### 1. User Profile Scrape (`is_cafe = false`)
- **Trigger:** SQS message with raw username string or `{ "username": "boardgamer123" }`.
- **Query:** `https://boardgamegeek.com/xmlapi2/collection?username={username}&subtype=boardgame&stats=1`
- **Output:** Parquet dataset at `s3://boardgame-app/data/users/{username}.parquet` with columns `['id', 'username', 'rating', 'own']`.
- **Downstream:** Triggers `bgg_taste_analytics` Lambda to compute TF-IDF taste profile.

### 2. Cafe Library Sync (`is_cafe = true`)
- **Trigger:** SQS message `{ "username": "maltandmeeple", "cafe_id": "the-malt-and-meeple", "is_cafe": true }`.
- **Query:** Queries BGG collection filtering strictly for owned games (`own=1`, `comments=1`, excluding expansions).
- **Shelf Location Parsing:** Applies regex extraction (`(?:Shelf|Location|Bin):?\s*([A-Za-z0-9\-]+)`) to game comments to extract physical shelf locations (e.g. `Shelf: B-3`).
- **Primary Storage:** Generates venue collection Parquet table at `s3://boardgame-app/data/cafes/{cafe_id}/collection.parquet`.
- **Pre-Rendered JSON Fast Path:** Simultaneously writes `s3://boardgame-app/data/cafes/{cafe_id}/collection.json` containing ready-to-serve JSON records so the patron collection browser loads in $<50\text{ms}$.

---

## Resilience & Rate Limiting

- **HTTP 202 Backoff:** When BGG returns `HTTP 202 (Accepted / Processing)`, the scraper backs off and retries with exponential backoff and randomized jitter (base 10s, max 60s).
- **Error Handling:** Handles missing tags, XML parsing errors, and malformed comments gracefully.
- **SQS Partial Batch Failures:** Reports `batchItemFailures` so failed records remain on the queue while successfully processed messages are deleted.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `S3_OUTPUT_BUCKET_NAME` | Target S3 bucket name | `boardgame-app` |
| `BGG_API_TOKEN` | Optional Bearer authorization token for BGG XML API2 | - |

---

## Local Development & Testing

Run unit tests:
```bash
pytest tests/test_bgg_user_data_scraper.py -v
```
