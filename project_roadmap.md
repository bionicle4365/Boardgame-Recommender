# Boardgame Recommender - Project Roadmap

This document outlines the next steps and architecture enhancements for the Boardgame Recommender project, aligned and structured to focus on caching performance, dynamic weights and BGG Hotness tuning, a dedicated Playgroup Organizer page, rich visual card metadata, and robust mock unit tests.

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
- [x] Limit SQS-to-Lambda trigger concurrency (e.g., using `reserved_concurrent_executions` or `max_concurrency` properties) in Terraform to regulate BGG outbound request concurrency.
- [x] Implement exponential back-off with random jitter retries in the scraper scripts (`bgg_game_scraper.py`, `bgg_game_data_scraper.py`, `bgg_user_data_scraper.py`).
- [x] Optimize checkpoint persistence frequency to limit duplicated scraped IDs upon container restart.

---

## Milestone 3: Serving Caching & API Performance Optimization

### Objective
Improve response times for active users, minimize Bedrock costs, and resolve cold-start latency.

### Tasks
- [x] Implement client-side `localStorage` caching on the frontend to instantly serve repeated searches.
- [x] Implement server-side recommendation caching in S3 (caching Bedrock-generated recommendation JSON files) with a 24-hour expiration TTL (aligned with the scraper update frequency).
- [x] Optimize Lambda container footprints and imports to reduce cold-start latency.

---

## Milestone 4: Recommender Enhancements & Dynamic Personalization UI

### Objective
Put recommendation parameters directly in the user's hands using sliders, including matching on current trending games.

### Tasks
- [x] Add smooth range sliders (0 to 100%) to the UI for weight dimensions: mechanics match, categories match, and popularity average.
- [x] Add a **Hotness / Trending Slider** that biases recommendations toward new, trending, or upcoming hot releases.
- [x] Scrape and parse the official BGG Hotness API feed dynamically or periodically to weight trending items in Bedrock and similarity scores.
- [x] Update the serving Lambda to compute similarity scoring using dynamic weights passed via query parameters from the frontend.
- [x] Save custom user weight profiles in the browser's `localStorage` to persist adjustments across visits.

---

## Milestone 5: Playgroup Organizer & Game Night Planner Page

### Objective
Create a dedicated space to manage board game night groups, select who is attending, and recommend games everyone will enjoy from their collectively owned libraries.

### Tasks
- [x] Build a new **Playgroups** layout page (`site_ui/groups/index.html`) featuring a clean dashboard to save and edit gaming groups.
- [x] Add controls to select which group members are attending a game night session.
- [x] Query and consolidate S3 profiles for all attending members to find games collectively owned by the group.
- [x] Generate recommendations from this combined library matching the exact attendance player count and optimizing for shared mechanic/theme profiles.

---

## Milestone 6: Rich Cards & CDN-Cached Image Rendering

### Objective
Upgrade recommendation card components to display visual thumbnails and key game statistics.

### Tasks
- [ ] Refactor game scrapers to parse and store BGG public image and thumbnail CDN URLs in the S3 Parquet database.
- [ ] Redesign recommendation cards in the Jekyll UI to render thumbnails directly from BGG's CDN.
- [ ] Render key metadata (complexity rating/weight, BGG rating, player count, play time) on recommendation cards.

---

## Milestone 7: Unit Testing & CI/CD Verification

### Objective
Write comprehensive unit tests with mocks to validate code correctness without spinning up containerized AWS mocks locally.

### Tasks
- [ ] Write pytest unit tests using `unittest.mock` to mock S3, SQS, and BGG API calls, keeping local testing lightweight.
- [ ] Configure automated test executions in GitHub Actions workflows to validate code on every branch push.
