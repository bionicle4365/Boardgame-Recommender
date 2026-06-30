---
name: BGG API Expert
description: Coordinates requests interacting with the BoardGameGeek (BGG) XML API2 and related API/scraped data endpoints.
---

## Guidelines for BGG API Operations

### BGG API Constraints & Behavior
- **API Version**: Use BGG XML API2 (`https://boardgamegeek.com/xmlapi2/...`).
- **Rate Limiting & Back-offs**: BGG API is rate-limited and often returns HTTP 202 (Accepted/Processing) when querying user collections. You MUST handle HTTP 202 by waiting and retrying with exponential backoff and jitter. Keep rate limit handling robust (e.g. SQS concurrency limiters, XML retry loops).
- **Caching**: Avoid redundant BGG API calls. Check the local S3 caches or client `localStorage` caching logic. Always prioritize cache lookups when implementing new fetches.

### Error Handling & Parsing
- Use `xml.etree.ElementTree` or `defusedxml` to safely parse XML payloads.
- Handle missing XML tags gracefully using default values. BGG data is frequently sparse (e.g. missing designer, missing publisher, or empty description).

### Key Files
- [bgg_game_scraper.py](file:///d:/Git/Boardgame-Recommender/bgg_game_scraper/bgg_game_scraper.py)
- [bgg_user_data_scraper.py](file:///d:/Git/Boardgame-Recommender/bgg_user_data_scraper/bgg_user_data_scraper.py)
- [test_bgg_user_data_scraper.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_user_data_scraper.py)
- [test_bgg_game_data_scraper.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_game_data_scraper.py)
