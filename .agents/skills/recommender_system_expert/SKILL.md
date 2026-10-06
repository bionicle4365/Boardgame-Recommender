---
name: recommender-system-expert
description: Responsible for the recommendation scoring pipeline, Bedrock LLM narration, table vibe engine, and real-time game night sessions. Use this skill when working on recommendation algorithms, scoring heuristics, Bedrock prompt engineering, caching, or session coordination.
---

## Guidelines for Recommendation Engineering

### Recommendation Logic & Algorithms
- **Modular Architecture**:
  - [scoring.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/scoring.py): Core heuristic scoring, duration/complexity pacing, taste distance, custom weight formulas, and Jaccard similarity.
  - [narration.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/narration.py): Bedrock prompt crafting and response parsing.
  - [cache_utils.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/cache_utils.py): Two-tier in-memory and S3 caching (`data/recommendation_cache/`, `data/similar_cache/`).
  - [sessions.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/sessions.py) & [session_handlers.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/session_handlers.py): Game night sessions, table voting tallies, and cafe table state management.
- **Cafe Table Vibe Engine**: Restricts candidate pool to `data/cafes/{cafe_id}/collection.parquet` when `cafe_id` is passed, filtering by vibe preset (e.g. party, casual strategy, two-player showdown) and table parameters.
- **Dislike Hard Exclusion**: Filter out candidate games dominated by the mechanics of disliked games (rating < 7.0 / thumbs down) from the Bedrock shortlist.
- **Deduplication**: Filter out variants, expansions, or duplicate editions using BGG relationships before passing to LLM.

### Bedrock LLM Grounding & Narration
- Uses Amazon Bedrock Nova Lite (`amazon.nova-lite-v1:0`) via the Converse API.
- Embed catalog mechanics directly into the Bedrock prompt to eliminate hallucinations.
- Apply tone rotation, opener uniqueness constraints, and fallback heuristic summaries if Bedrock calls fail.

### S3 Data & Parquet Access
- Master catalog: `data/boardgames_combined/catalog.parquet`.
- User collection profiles: `data/users/{username}.parquet`.
- Cafe libraries: `data/cafes/{cafe_id}/collection.parquet`.
- Optimize reads by caching datasets in-memory across Lambda container warm invocations.

### Key Files
- [bgg_recommender.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/bgg_recommender.py)
- [scoring.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/scoring.py)
- [narration.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/narration.py)
- [cache_utils.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/cache_utils.py)
- [sessions.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/sessions.py)
- [session_handlers.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/session_handlers.py)
- [test_bgg_recommender.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_recommender.py)
- [test_narration.py](file:///d:/Git/Boardgame-Recommender/tests/test_narration.py)
- [test_cache_utils.py](file:///d:/Git/Boardgame-Recommender/tests/test_cache_utils.py)
- [test_game_night_sessions.py](file:///d:/Git/Boardgame-Recommender/tests/test_game_night_sessions.py)
