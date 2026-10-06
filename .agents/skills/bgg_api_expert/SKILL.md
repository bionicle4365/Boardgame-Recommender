---
name: bgg-api-expert
description: Coordinates requests interacting with the BoardGameGeek (BGG) XML API2, CORS API proxy, convention preview scraper, and related ingestion Lambdas. Use this skill when modifying scrapers, parsing BGG XML, managing API proxy routes, or handling BGG rate limits and HTTP 202 retry logic.
---

## Guidelines for BGG API Operations

### BGG API Constraints & Behavior
- **API Version**: Use BGG XML API2 (`https://boardgamegeek.com/xmlapi2/...`).
- **Rate Limiting & Back-offs**: BGG API is rate-limited and often returns HTTP 202 (Accepted/Processing) when querying user collections. You MUST handle HTTP 202 by waiting and retrying with exponential backoff and jitter. Keep rate limit handling robust (e.g. SQS concurrency limiters, XML retry loops).
- **Client CORS Reverse Proxy**: [bgg_api_proxy/bgg_api_proxy.py](file:///d:/Git/Boardgame-Recommender/bgg_api_proxy/bgg_api_proxy.py) provides browser-safe client collection fetching without CORS errors, injecting `BGG_API_TOKEN` server-side and validating username regex (`^[a-zA-Z0-9_]{1,25}$`).
- **High-Throughput Batch Game Ingestion**: [bgg_game_data_scraper/bgg_game_data_scraper.py](file:///d:/Git/Boardgame-Recommender/bgg_game_data_scraper/bgg_game_data_scraper.py) fetches 100 game IDs per call (`?id=1,2,...,100&stats=1`) via SQS batching to maximize throughput under rate limits.
- **Convention Preview Harvester**: [bgg_preview_refresh/bgg_preview_refresh.py](file:///d:/Git/Boardgame-Recommender/bgg_preview_refresh/bgg_preview_refresh.py) discovers upcoming convention previews (Essen Spiel, Gen Con, Origins) and stores metadata in S3.
- **Caching**: Avoid redundant BGG API calls. Check local S3 caches or client `localStorage` caching logic. Always prioritize cache lookups when implementing new fetches.

### Error Handling & Parsing
- Use `xml.etree.ElementTree` or `defusedxml` to safely parse XML payloads.
- Handle missing XML tags gracefully using default values. BGG data is frequently sparse (e.g. missing designer, missing publisher, or empty description).

### Key Files
- [bgg_api_proxy.py](file:///d:/Git/Boardgame-Recommender/bgg_api_proxy/bgg_api_proxy.py)
- [bgg_game_data_scraper.py](file:///d:/Git/Boardgame-Recommender/bgg_game_data_scraper/bgg_game_data_scraper.py)
- [bgg_user_data_scraper.py](file:///d:/Git/Boardgame-Recommender/bgg_user_data_scraper/bgg_user_data_scraper.py)
- [bgg_preview_refresh.py](file:///d:/Git/Boardgame-Recommender/bgg_preview_refresh/bgg_preview_refresh.py)
- [bgg_game_scraper.py](file:///d:/Git/Boardgame-Recommender/bgg_game_scraper/bgg_game_scraper.py)
- [test_bgg_api_proxy.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_api_proxy.py)
- [test_bgg_game_data_scraper.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_game_data_scraper.py)
- [test_bgg_user_data_scraper.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_user_data_scraper.py)
- [test_bgg_preview_refresh.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_preview_refresh.py)
