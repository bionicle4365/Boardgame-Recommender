# Recommender Rules (`bgg_recommender/`)

- **Module Separation**: Maintain strict separation between `scoring.py` (deterministic heuristics and similarity math), `narration.py` (Amazon Bedrock Nova Lite Converse prompting and fallbacks), `cache_utils.py` (in-memory and S3 caching), and `sessions.py` / `session_handlers.py` (game night sessions and table voting).
- **Contract & Schema Sync**: Read `docs/contracts/schemas_and_routes.json` before changing routes or reading/writing Parquet columns. Update `docs/contracts/schemas_and_routes.json` if any route or payload schema changes.
- **Testing**: Run `python -m pytest tests/test_bgg_recommender.py tests/test_narration.py tests/test_cache_utils.py tests/test_game_night_sessions.py` (or `python -m pytest`) after edits.
