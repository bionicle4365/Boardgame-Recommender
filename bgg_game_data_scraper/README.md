# BGG Game Data Scraper Lambda

An asynchronous, SQS-triggered containerized AWS Lambda worker that consumes board game IDs from the game queue, fetches complete game statistics and metadata from the BoardGameGeek (BGG) XML API2, and writes normalized single-game Parquet files into the S3 raw data lake.

---

## Architecture Overview

```mermaid
graph LR
    Queue[SQS: bgg-game-queue] -->|Batch up to 20 IDs| Lambda[BGG Game Data Scraper Lambda]
    Lambda -->|XML API2 /thing?id=...&stats=1| BGG[BoardGameGeek API]
    BGG -->|XML Payload| Lambda
    Lambda -->|Parse & Map Schema| PyArrow[PyArrow Parquet Writer]
    PyArrow -->|Upload raw/{game_id}.parquet| S3[(S3: boardgame-app/raw/)]
```

---

## Key Features

1. **Batch Ingestion (Up to 20 Games per Call):**
   - BGG's `/thing` endpoint accepts comma-separated IDs (e.g. `?id=1,2,3&stats=1`).
   - The scraper chunks incoming SQS records into batches of up to 20 IDs, maximizing API throughput while adhering to BGG rate limits.
2. **Defensive XML Parsing:**
   - Robustly handles missing tags, sparse descriptions, and HTML entities (`&#10;`).
   - Parses community poll data for optimal player count (`suggested_players_best` and `suggested_players_recommended`).
3. **Columnar Parquet Output:**
   - Serializes each game into an individual Snappy-compressed Parquet file under `s3://{bucket}/raw/{game_id}.parquet`.
   - These raw files are subsequently aggregated into the master catalog by [`bgg_compactor`](file:///d:/Git/Boardgame-Recommender/bgg_compactor).
4. **Resilience & Rate Limit Handling:**
   - Automatic exponential backoff with jitter on HTTP 429 / 5xx responses.
   - SQS Dead Letter Queue (DLQ) captures persistent failures for debugging.

---

## Output Schema (`raw/{game_id}.parquet`)

| Field | Type | Description |
|---|---|---|
| `id` | `string` | BGG game ID. |
| `type` | `string` | BGG item type (`boardgame`, `boardgameexpansion`). |
| `name` | `string` | Primary title. |
| `year_published` | `int64` | Publication year. |
| `min_players` / `max_players` | `int64` | Supported player range. |
| `playing_time` / `min_playtime` / `max_playtime` | `int64` | Playtime duration in minutes. |
| `min_age` | `int64` | Minimum recommended age. |
| `rating` | `float64` | BGG Bayes average rating (Geek rating, 1.0–10.0). |
| `complexity` | `float64` | Community weight / rules complexity (1.0–5.0). |
| `thumbnail` / `image` | `string` | Box art URLs. |
| `categories` | `list<string>` | Categories (e.g. `Economic`, `Fantasy`). |
| `mechanics` | `list<string>` | Game mechanics (e.g. `Worker Placement`, `Dice Rolling`). |
| `designers` / `publishers` | `list<string>` | Credited individuals and companies. |
| `suggested_players_best` | `list<string>` | Player counts voted "Best" by community. |
| `suggested_players_recommended` | `list<string>` | Player counts voted "Recommended" by community. |

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `S3_OUTPUT_BUCKET_NAME` | Target S3 bucket for raw parquet storage | `boardgame-app` |
| `LOG_LEVEL` | Logging verbosity (`INFO`, `DEBUG`, `WARNING`) | `INFO` |

---

## Local Development & Testing

Run unit tests for XML parsing and Parquet generation:
```bash
pytest tests/test_bgg_game_data_scraper.py -v
```

Deploy container updates via GitHub Actions workflow:
- [`.github/workflows/data-scraper-docker-image.yml`](file:///d:/Git/Boardgame-Recommender/.github/workflows/data-scraper-docker-image.yml)
