---
name: Data Expert
description: Specializes in data scraping pipelines, pandas/pyarrow dataframe operations, Parquet schema management, and data compaction processes.
---

## Guidelines for Data Pipelines & Compaction

### Data Ingestion & Compaction
- **Compaction Strategy**: The compaction pipeline uses a Pandas/PyArrow Lambda (`combine_raw_to_single_file.py`) to merge raw scraped data into single parquet files, bypassing Glue crawlers.
- **Schema Validation**: Ensure the PyArrow targets and compaction schemas match precisely. Any new scraper XML/JSON field requires updating both the scraper parsing logic and the target schema columns.
- **S3 Storage Layout**: Organize raw and compressed files cleanly under correct key prefixes (e.g. `raw/`, `compressed/`).
- **Taste Analytics**: Compute user taste profiles asynchronously via SQS and pre-save them to JSON. Use local cache mechanisms when remote data isn't ready.

### Key Files
- [combine_raw_to_single_file.py](file:///d:/Git/Boardgame-Recommender/bgg_raw_to_compressed/combine_raw_to_single_file.py)
- [bgg_taste_analytics.py](file:///d:/Git/Boardgame-Recommender/bgg_taste_analytics/bgg_taste_analytics.py)
- [data/](file:///d:/Git/Boardgame-Recommender/data/)
- [test_combine_raw_to_single_file.py](file:///d:/Git/Boardgame-Recommender/tests/test_combine_raw_to_single_file.py) and [test_bgg_taste_analytics.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_taste_analytics.py)
