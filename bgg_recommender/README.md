# Serving Recommendation Lambda API (`bgg_recommender`)

This directory contains the containerized AWS Lambda function that powers personalized AI board game recommendations, content-based candidate ranking, Amazon Bedrock (Nova Micro) sommelier narrations, and real-time game night table voting sessions.

---

## Architecture & Modular Components

```mermaid
graph TD
    Client[Web / Mobile Patron Client] -->|GET /recommendations, POST /cafe/vote/start| APIGW[API Gateway]
    APIGW --> Handler[bgg_recommender.py]
    
    Handler --> Route{Route Match}
    Route -->|/recommendations| Engine[Recommendation Engine]
    Route -->|/session, /cafe/vote/start| SessHandler[session_handlers.py]
    
    Engine --> Scoring[scoring.py<br/>Cosine Sim & Gaussian Decay]
    Engine --> Narration[narration.py<br/>Bedrock Nova Micro Sommelier]
    Engine --> Cache[cache_utils.py<br/>S3 Caches & Cafe Inventory]
    
    SessHandler --> Sessions[sessions.py<br/>Voting & Consensus Engine]
    Sessions --> DDBSess[(DynamoDB: bgg-game-night-sessions)]
    
    Cache --> S3Catalog[(S3: catalog.parquet)]
    Cache --> S3Cafe[(S3: data/cafes/{cafe_id}/collection.parquet)]
    Cache --> S3Cache[(S3: data/recommendation_cache/)]
```

### Module Directory Breakdown

* **`bgg_recommender.py`**: Main AWS Lambda handler entry point. Routes `/recommendations`, `/profile`, `/conventions`, and session paths (`/session`, `/sessions`, `/cafe/vote/start`). Manages SQS scrape dispatch on cache misses.
* **`scoring.py`**: Core deterministic scoring pipeline:
  - **Tag Affinity (TF-IDF & Cosine Similarity):** True cosine similarity dividing tag dot products by candidate vector norms $\sqrt{|\text{cand\_tags}|}$.
  - **Continuous Gaussian Complexity Decay:** Replaces hard buckets with distance decay centered on target/user mean complexity ($\sigma = 0.75$).
  - **Cafe Vibe Weight Vectors:** Pre-configured Gaussian curves and mechanic affinity matrices for table vibes (`party`, `casual_strategy`, `deep_strategy`, `cooperative`, `direct_conflict`).
  - **Candidate Diversification:** Deterministic multi-tag post-scoring pass to prevent category and mechanic clustering in shortlists.
* **`narration.py`**: Bedrock LLM grounding and narration engine:
  - Employs Amazon Nova Micro with high-temperature conversational grounding.
  - Dedicated **Cafe Sommelier Persona** prompt emphasizing rules teach times, table atmosphere over drinks, group banter, and shelf locations.
  - Injects candidate mechanics to eliminate LLM hallucinations.
  - Enforces strict 1-sentence explanations (20–28 words) with diverse openers.
* **`session_handlers.py`**: Route handlers for voting session operations:
  - `POST /cafe/vote/start`: Single-tap cafe table session initialization prepopulated with top recommended games and formatted as `"{Cafe Name} - Table {Table Number}"`.
  - `POST /session`, `GET /session`, `POST /session/vote`, `POST /session/close`, `DELETE /session`, `GET /sessions`.
* **`sessions.py`**: State machine and DynamoDB persistence layer for table voting sessions using $+2$ (Favorite), $+1$ (Interested), and $-99$ (Veto) consensus scoring.
* **`cache_utils.py`**: In-memory and S3 caching layer:
  - `get_cafe_inventory(cafe_id)`: Loads cafe library with in-memory caching and S3 parquet fallback.
  - `get_cached_recommendations(cache_key)`: Smart cache invalidation ensuring recommendations are newer than the profile.
  - `get_catalog()`: Downloads and caches `catalog.parquet` into Lambda `/tmp`.
* **`Dockerfile`**: Container image definition for deployment to Amazon ECR and AWS Lambda.

---

## API Endpoints

### 1. `GET /recommendations`
- **Standard Mode:** `?username=boardgamer123&player_count=4&duration_pref=medium`
- **Cafe Sommelier Mode:** `?cafe_id=the-malt-and-meeple&vibe=casual_strategy&player_count=4&duration_pref=medium&table=7`
  - Restricts candidate pool strictly to the cafe's owned inventory (`own=1`).
  - Generates recommendations even for patrons without BGG accounts.
  - Returns shelf coordinates (e.g. `📍 Shelf B-3`), estimated rules teach times, rules video links, and Bedrock sommelier quotes.

### 2. `POST /recommendations`
- Accepts inline weight overrides and taste test / personality quiz inputs for cold-start users.

### 3. `POST /cafe/vote/start`
- **Payload:**
  ```json
  {
    "cafe_id": "the-malt-and-meeple",
    "cafe_name": "The Malt & Meeple",
    "table": "4",
    "candidates": [ ...top recommendations... ]
  }
  ```
- **Response:** Creates voting session in DynamoDB and returns `{ session_id, vote_url, ... }`.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `S3_OUTPUT_BUCKET_NAME` | S3 data lake bucket name | `boardgame-app` |
| `USER_SQS_QUEUE_URL` | SQS queue URL for collection scraping jobs | - |
| `BEDROCK_MODEL_ID` | Amazon Bedrock LLM identifier | `amazon.nova-lite-v1:0` |
| `DYNAMODB_SESSIONS_TABLE_NAME` | DynamoDB table name for game night voting sessions | `bgg-game-night-sessions` |

---

## Local Development & Testing

Run the full recommender test suite:
```bash
pytest tests/test_bgg_recommender.py tests/test_narration.py tests/test_cache_utils.py tests/test_game_night_sessions.py -v
```
