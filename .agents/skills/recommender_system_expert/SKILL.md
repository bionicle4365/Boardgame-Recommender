---
name: Recommender System Expert
description: Responsible for the recommendation scoring pipeline and Bedrock integration.
---

## Guidelines for Recommendation Engineering

### Recommendation Logic & Algorithms
- **Heuristic Scoring**: Keep duration, complexity pacing, and user taste alignment weights properly balanced.
- **Dislike Hard Exclusion**: Filter out candidate games dominated by the mechanics of disliked games (rating < 7.0 / thumbs down) from the Bedrock shortlist.
- **Deduplication**: Filter out variants, expansions, or duplicate editions using BGG relationships (`boardgamefamily`, etc.) before passing to LLM.

### Bedrock LLM Grounding
- Embed catalog mechanics directly into the Bedrock Converse API prompt to eliminate hallucinations.
- Apply high-temperature settings, explicit 7-angle rotation instructions, and strict opener uniqueness constraints.

### S3 Data & Parquet Access
- **Catalog Parquet Location**: The combined game catalog is stored at S3 key `data/boardgames_combined/catalog.parquet` in the project's data bucket.
- **User Parquet Location**: Individual user collection profiles are stored at S3 key `data/users/{username}.parquet`.
- **Retrieval**: Download parquet files to the local ephemeral directory `/tmp/` before reading/processing with `pandas` or `pyarrow`. Keep S3 calls optimized and cache the catalog in-memory where applicable.

### Key Files
- [bgg_recommender.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/bgg_recommender.py)
- [test_bgg_recommender.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_recommender.py)
