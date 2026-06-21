# Boardgame Recommender - Project Roadmap

This document outlines the next steps and active architecture enhancements for the Boardgame Recommender project.

---

## Milestone 8: Database Reprocessing & Full Catalog Scrape Execution

### Objective
Execute the scraper and serverless compaction Lambda pipeline to capture the new metadata fields for the entire board game catalog database.

### Tasks
- [ ] Run `bgg_game_scraper.py` in reprocess mode to queue existing S3 game IDs.
- [ ] Monitor background SQS scraper workers to ensure the catalog is fully updated with complexity, ratings, playtime, and image URLs.
- [ ] Invoke the serverless python compaction Lambda (`bgg_compactor`) to consolidate individual raw game Parquet files into the unified `catalog.parquet` file in S3.
- [ ] Verify that the compacting Lambda runs successfully within memory and execution time limits for the full dataset.

---

## Milestone 9: Advanced Filter Builder (Hard Exclusions & Designer Weights)

### Objective
Add advanced UI filters to exclude specific categories, mechanics, or designers, and perform dynamic filtering in Python before calling Bedrock.

### Tasks
- [ ] Implement exclusion UI multi-select lists for mechanics, categories, and designers.
- [ ] Update frontend script to deliver exclusion collections as URL query parameters.
- [ ] Update serving Lambda backend to dynamically parse exclusions and filter candidates in Python prior to Bedrock invocation.

---

## Milestone 11: Playgroup Taste Profile & Visualizations

### Objective
Construct visual taste profile charts displaying a playgroup's collective mechanic and category preferences.

### Tasks
- [ ] Import `Chart.js` via CDN on the playgroup dashboard page.
- [ ] Aggregate categories and mechanics counts dynamically based on the collective collection of attending members.
- [ ] Render a responsive radar chart (for mechanics) and bar chart (for categories) showing group taste profile details.

---

## Milestone 14: Recommender Personalization via Duration & Complexity Weighting

### Objective
Enhance the recommendation engine by allowing users to weight their preferences for game length (Short/Medium/Long) and complexity (Low/Medium/High) without applying hard exclusions.

### Tasks
- [ ] **UI Controls:** Add interactive weight profile buttons/menus on both the Recommender and Playgroups pages for Play Time (Short/Medium/Long/Any) and Complexity (Low/Medium/High/Any) preferences.
- [ ] **Parameter Passing:** Update the frontend client script to forward these preferences as query parameters (`duration_pref`, `complexity_pref`) to the recommender API.
- [ ] **Dynamic Weighting Algorithm:** Update [bgg_recommender.py](file:///d:/Git/Boardgame-Recommender/bgg_recommender/bgg_recommender.py) to map these categories to numeric thresholds (e.g., Short < 45m, Long > 90m; Low < 2.0, High > 3.5) and compute a similarity score bias based on proximity.
- [ ] **Bedrock Prompt Integration:** Include the user's length and complexity preferences in the Bedrock LLM system context so that the generated recommendation explanations ("reasons") highlight why the game matches their preferred pacing and weight.
- [ ] **Unit Tests:** Add comprehensive unit tests in [test_bgg_recommender.py](file:///d:/Git/Boardgame-Recommender/tests/test_bgg_recommender.py) to verify weighting calculation correctness and parameter validation.

---

## Milestone 15: User Authentication & Profile Persistence

### Objective
Secure the recommendation and playgroup endpoints using Amazon Cognito User Pools and enable authenticated users to save customized taste profiles, weight presets, and playgroups to persistent storage.

### Tasks
- [ ] **Cognito Integration:** Configure an Amazon Cognito User Pool and Client in Terraform to handle secure user registration, verification, login, and token generation.
- [ ] **Frontend Login Flow:** Integrate a custom embedded login modal/screen in the UI using clean Vanilla CSS and Javascript to handle user signup, login, and secure token caching (avoiding redirect Hosted UI).
- [ ] **API Security:** Secure API Gateway endpoints by configuring a Cognito Authorizer in Terraform, requiring clients to pass a valid ID/Access token.
- [ ] **User Profile Storage:** Implement a DynamoDB table keyed by Cognito user IDs (`sub`) to persistently save, retrieve, and share customized playgroups, weights, and recommendation histories (leveraging DynamoDB Free Tier).
- [ ] **Unit and Integration Tests:** Author mock test suites to verify authorizer route protection and profile persistence APIs.

---

## Milestone 16: Collection Browser Analyzer & Library Analytics Dashboard

### Objective
Enhance the BGG Collection Browser with an embedded visual analytics dashboard tab showing play counts, rating comparisons, and distribution charts for playtimes and player counts using Chart.js.

### Open Questions
- **Dynamic Filtering Interaction:** Should the analytics dashboard charts automatically filter based on active search queries and faceted filters (e.g., clicking "Duet 2 Players" filters the table and updates all charts to reflect only those 2-player games)? Or should the analytics always represent the entire imported library?
- **Handling N/A Ratings:** If a user has only rated a few games, the personal rating distribution chart will have mostly `N/A` values. Should the chart fall back to showing BGG rating distribution, or only analyze games with valid user ratings?
- **CSV/JSON Export:** Should the browser provide an option to download the parsed collection data as a clean CSV or JSON file for offline user analysis?

### Tasks
- [ ] **Tabbed UI Design:** Refactor [index.html](file:///d:/Git/Boardgame-Recommender/site_ui/collection/index.html) to support tab buttons ("Grid View" and "Collection Analytics") and clear view panels.
- [ ] **Summary Cards:** Create glassmorphism summary cards displaying key library stats (Total Games, Average Personal vs BGG Rating, Total Plays, #1 Played Game).
- [ ] **Chart.js Integration:** Load Chart.js via CDN and implement responsive chart containers for playtime, player count, rating distributions, and most played leaderboards.
- [ ] **Dynamic Data Wiring:** Write Javascript triggers that extract stats from `gamesData` (and optionally react to active filters) to update the Chart.js instances.

---

## Milestone 17: Cold-Start Onboarding (BGG Profile Bypass & Rating Flow)

### Objective
Provide a seamless recommendation flow for users without a BoardGameGeek profile by presenting a curated onboarding list of 10 popular/common board games and letting them rate (Thumbs Up/Down/Skip) to initialize their interest profile.

### Tasks
- [ ] **Curated Seed Catalog:** Curate a distinct list of 10 to 15 widely recognized board games across diverse genres (e.g., Catan, Ticket to Ride, Pandemic, Codenames, 7 Wonders, Azul, Wingspan, Dominion, Scythe, Gloomhaven) to serve as initial seeds.
- [ ] **Onboarding UI Component:** Design a responsive, card-based carousel/modal onboarding wizard in the frontend where users can click Thumbs Up / Thumbs Down / Skip.
- [ ] **Mock Profile Construction:** Package the user's manual rating selections into a standardized temporary JSON payload structure matching the backend schema (mapping likes to 9.0, dislikes to 3.0, and skipping ignored items).
- [ ] **API Endpoint Support:** Update the API gateway and the `bgg_recommender` Lambda backend to support receiving this raw inline user profile payload directly, bypassing the S3 profile load step.
- [ ] **Onboarding Unit Tests:** Implement backend unit tests verifying the recommendation generator executes successfully when provided directly with mock/onboarded profile data payloads.

---

## Completed Milestones

* **Milestone 1: Crawler & Data Pipeline Verification** (AWS S3 combined catalog downloads, custom Parquet schema mapping)
* **Milestone 2: Scraper Resilience, Concurrency Limiting, & API Back-off** (SQS rate limiting, exponential backoff/jitter)
* **Milestone 3: Serving Caching & API Performance Optimization** (S3 and client localStorage caching)
* **Milestone 4: Recommender Enhancements & Dynamic Personalization UI** (weights, BGG hotness tuning, dynamic parameters)
* **Milestone 5: Playgroup Organizer & Game Night Planner Page** (attendee filtering, group collection merging)
* **Milestone 6: Rich Cards & CDN-Cached Image Rendering** (metadata display, visual image cards)
* **Milestone 7: Unit Testing & CI/CD Verification** (pytest, GitHub Actions workflows)
* **Milestone 10: Mobile UI Optimization & Responsive Navigation Menu** (responsive layouts, blurred backdrop mobile drawer)
* **Milestone 12: Production Observability, Rate Limiting, & Cost Protection** (API limits, structured logging, alarms)
* **Milestone 13: Serverless Cost Optimization & Glue Crawler Bypass** (Python pandas/pyarrow compaction Lambda, bypass Athena)
