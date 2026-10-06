---
name: data-expert
description: Specializes in data scraping pipelines, pandas/pyarrow dataframe operations, S3 Parquet datasets, schema management, and data compaction processes. Use this skill when working with tabular datasets, Parquet schemas, S3 lake layouts, or compaction logic.
---

## Guidelines for Data Pipelines & Compaction

### Data Ingestion & Compaction
- **Compaction Strategy**: The compaction pipeline uses a Pandas/PyArrow container Lambda ([bgg_compactor/combine_raw_to_single_file.py](file:///d:/Git/Boardgame-Recommender/bgg_compactor/combine_raw_to_single_file.py)) to merge raw scraped data into single parquet files, bypassing Glue crawlers and Athena queries.
- **S3 Data Lake Layout**:
  - Combined Catalog: `data/boardgames_combined/catalog.parquet` (master catalog used by recommender and sommelier).
  - User Collections: `data/users/{username}.parquet`.
  - Cafe Libraries: `data/cafes/{cafe_id}/collection.parquet` and `data/cafes/{cafe_id}/meta.json`.
  - Cafe Registry: `data/cafes_registry.json`.
  - Convention Previews: `data/active_previews.json` and `data/active_previews_games.json`.
  - Cache Storage: `data/recommendation_cache/` and `data/similar_cache/`.
- **Schema Validation**: Ensure PyArrow target types and compaction schemas match precisely. Any new scraper XML/JSON field requires updating both the scraper parsing logic and the target schema columns.
- **Cafe Collection Ingestion**: Supported in [bgg_user_data_scraper.py](file:///d:/Git/Boardgame-Recommender/bgg_user_data_scraper/bgg_user_data_scraper.py) when `is_cafe=true`, isolating owned games (`own=1`) and extracting shelf location notes from BGG comments.
- **Taste Analytics**: Compute user taste profiles asynchronously via SQS and pre-save them to JSON. Use local cache mechanisms when remote data isn't ready.

### Key Files
- [combine_raw_to_single_file.py](file:///d:/Git/Boardgame-Recommender/bgg_compactor/combine_raw_to_single_file.py)
- [bgg_taste_analytics.py](file:///d:/Git/Boardgame-Recommender/bgg_taste_analytics/bgg_taste_analytics.py)
- [bgg_user_data_scraper.py](file:///d:/Git/Boardgame-Recommender/bgg_user_data_scraper/bgg_user_data_scraper.py)
- [test_combine_raw_to_single_file.py](file:///d:/Git/Boardgame-Recommender/tests/test_combine_raw_to_single_file.py)
- [test_bgg_taste_analytics.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_taste_analytics.py)
- [test_cafe_sync.py](file:///d:/Git/Boardgame-Recommender/tests/test_cafe_sync.py)
