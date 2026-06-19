# Boardgame Recommender - Project Roadmap

This document outlines the next steps and architecture enhancements for the Boardgame Recommender project, prioritized logically to focus on immediate pipeline fixes, API safety, core UI usability, visual analytics, and caching.

---

## Milestone 1: Crawler & Data Pipeline Verification (Coalescing & Download Optimization)

### Objective
Optimize the AWS Glue ETL compaction script to write consolidated Parquet files, verify the end-to-end raw-to-combined data pipeline, and speed up Lambda catalog download times.

### Tasks
- [x] Refactor the PySpark ETL script (`combine_raw_to_single_file.py`) to coalesce dynamic frame partitions to `1` so it writes a single compressed Parquet file to S3.
- [x] Monitor the catalog scraper progress to ensure it has successfully processed the full target range of BoardGameGeek game IDs.
- [x] Trigger and run the AWS Glue Crawler to scan the raw catalog dataset.
- [x] Execute the compaction Glue job (`boardgame_app_combine_job`) to consolidate raw JSON/Parquet records into the single combined catalog file.
- [x] Refactor `bgg_recommender/bgg_recommender.py` loading logic to fetch this single catalog Parquet file directly from S3, completely bypassing listing and loop downloads to eliminate container cold-start delay.
- [x] Verify that the combined database table schema mapping successfully handles newly scraped fields (such as `year_published`).

---

## Milestone 2: Scraper Resilience, Concurrency Limiting, & API Back-off

### Objective
Protect the BGG XMLAPI2 endpoint from concurrent request spikes, implement robust retry mechanisms, and avoid rate limiting or IP blocks.

### Tasks
- [ ] Limit SQS-to-Lambda trigger concurrency (e.g., using `reserved_concurrent_executions` or `max_concurrency` properties) in Terraform to regulate BGG outbound request concurrency.
- [ ] Implement exponential back-off with random jitter retries in the scraper scripts (`bgg_game_scraper.py`, `bgg_game_data_scraper.py`, `bgg_user_data_scraper.py`).
- [ ] Optimize checkpoint persistence frequency to limit duplicated scraped IDs upon container restart.

---

## Milestone 3: Interactive Collection Browser Enhancements

### Objective
Scale the collection browser to handle large lists, adding user controls for sorting and filtering.

### Tasks
- [x] Implement client-side pagination or virtual scrolling for the collection table.
- [x] Add interactive column sorting for key attributes (e.g., rating, play time, name).
- [x] Build advanced multi-select tag filter components.

---

## Milestone 4: Advanced Frontend Analytics Dashboard

### Objective
Enrich the Jekyll UI with collection visual analytics.

### Tasks
- [ ] Integrate a charting library (like Chart.js or custom SVG charts) into the Jekyll UI pages.
- [ ] Build a dashboard presenting collection distribution statistics (e.g., categories breakdown donut chart, complexity ranges bar chart, player count distribution).

---

## Milestone 5: Caching & Serving API Performance Optimization

### Objective
Improve response times for active users, minimize Bedrock costs, and reduce duplicate scraper invocations.

### Tasks
- [ ] Implement client-side `localStorage` caching on the frontend to instantly serve repeated searches.
- [ ] Implement server-side recommendation caching (e.g., caching generated JSON results in S3).
- [ ] Optimize Lambda container footprints to further reduce cold-start latency.
