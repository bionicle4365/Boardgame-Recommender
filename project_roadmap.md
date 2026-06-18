# Boardgame Recommender - Project Roadmap

This document outlines the next steps and architecture enhancements for the Boardgame Recommender project.

---

## Milestone 1: Crawler & Data Pipeline Verification

### Objective
Verify the end-to-end data pipeline from raw scraped data in S3 to the combined board game catalog, ensuring correct schema mapping and data density.

### Tasks
- [ ] Monitor the catalog scraper progress to ensure it has successfully processed the full target range of BoardGameGeek game IDs.
- [ ] Trigger and run the AWS Glue Crawler to scan the raw catalog dataset.
- [ ] Run the Glue ETL compaction job (`boardgame_app_combine_job`) to consolidate raw records into the combined table.
- [ ] Run verification queries (via Athena/Python) to ensure the combined table contains all newly crawled game metadata (such as `year_published`) and matches row count expectations.

---

## Milestone 2: Advanced Frontend Analytics Dashboard

### Objective
Enrich the Jekyll website with collection metrics and visualizations to provide users with visual insights into their gaming catalog.

### Tasks
- [ ] Integrate a charting library (e.g., Chart.js or vanilla SVG charts) into the Jekyll UI layout.
- [ ] Implement a dashboard layout showing:
  - Category and mechanics breakdown (e.g., pie/donut chart of most played genres).
  - Complexity (weight) distribution (e.g., bar chart of game weight ranges).
  - Optimal player count ranges.
  - Rating distribution of their rated boardgames.

---

## Milestone 3: Interactive Collection Browser Enhancements

### Objective
Improve user controls and scalability of the BGG Collection Browser table.

### Tasks
- [ ] Implement client-side pagination or virtual scrolling to seamlessly display collections with hundreds of games.
- [ ] Add interactive column sorting (sorting by rating, weight, play time, name).
- [ ] Create advanced multi-select filter components (e.g., filtering by complexity range, player count, category tags).

---

## Milestone 4: Scraper Resilience & Deduplication

### Objective
Ensure scraper jobs are reliable, handle rate limiting gracefully, and produce clean, optimized Parquet outputs.

### Tasks
- [ ] Add robust exponential back-off and retry logic in `bgg_game_scraper` and `bgg_user_data_scraper` to handle BGG API throttling.
- [ ] Implement deduplication logic to prevent redundant writes or overlapping records in raw S3 Parquet files.
- [ ] Optimize S3 directory structures and partitioning schemes.

---

## Milestone 5: Serving API Performance Optimization & Caching

### Objective
Speed up recommendations serving API requests and lower Bedrock token usage by caching query outputs.

### Tasks
- [ ] Implement a recommendation cache (e.g., JSON files in an S3 prefix like `data/recommendation_cache/{username}.json` or DynamoDB storage).
- [ ] Add caching for BGG collection api proxy queries to prevent repeating slow scraping calls for active users.
- [ ] Optimize Lambda container initialization and dependency footprint for faster cold-start times.
