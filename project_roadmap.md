# Boardgame Recommender - Project Roadmap

This document outlines the next steps and active architecture enhancements for the Boardgame Recommender project.

---

## Milestone 9: Crowdfunding Tracker (Kickstarter, Gamefound, & Backerkit Integration)

### Objective
Sync active board game crowdfunding campaigns (Kickstarter, Gamefound, Backerkit) and recommend them to users based on their existing taste profiles, allowing them to discover upcoming games before they hit retail.

### Design Notes
**Data Retrieval Strategy:**
- **Gamefound**: Has a clean, public JSON API (`GET /api/public/projects/getActiveCrowdfundingProjects`) that we can call directly.
- **Backerkit**: Needs to be investigated for an API. If none exists, we will apply the same scraping strategy used for Kickstarter.
- **Kickstarter**: Lacks a public API. We will reuse the ECS Fargate Playwright task (already implemented for BGG conventions) to scrape the Tabletop Games Discover page to extract campaign URLs, thumbnails, and funding statistics.

### Tasks
- [ ] **Crowdfunding Scraper (ECS Fargate):** Implement a weekly scraper to fetch active board game campaigns from Kickstarter, Gamefound, and Backerkit, extracting metadata (mechanics, theme, designer, pledge levels).
- [ ] **Campaign Persistence:** Store active campaign data in an S3 JSON file or DynamoDB table for rapid frontend access.
- [ ] **Scoring Integration:** Update the Python Lambda backend to load the active campaign catalog and score it against the user's taste profile, keeping crowdfunding recommendations in a separate "Upcoming/Crowdfunding" UI lane.
- [ ] **Frontend Crowdfunding Lane:** Build a dedicated horizontal scroll lane or tab in the UI specifically for live crowdfunding campaigns, complete with "Days Remaining" and "Funding Status" badges.

---

## Milestone 17: Cold-Start Onboarding (BGG Profile Bypass & Rating Flow)

 ### Objective
 Provide a seamless recommendation flow for users without a BoardGameGeek profile or a profile that doesn't have enough data. The user is walked through a two-round adaptive game rating flow (👍 / 👎 / Haven't played it) that collects enough signal to build a temporary taste profile, which is submitted inline to the existing recommendation API.

 ### Design Notes

 **Why only positive ratings build the weight profile (and what we do about it):**
 The recommender's scoring weights are built exclusively from liked games (rating >= 7.0). Disliked games (rating 3.0) are excluded from the weight-building step — they do not penalise mechanics in candidate scoring. For a full BGG profile (15+ liked games), positive signal alone is dense enough that this is not a significant limitation. For the cold-start case (3-8 liked games), disliked games represent meaningful signal that must not be silently discarded. The solution is a **hard candidate exclusion** rather than negative weight subtraction: after scoring, any candidate game whose primary mechanics are dominated by mechanics from disliked games (with no overlap with liked mechanics) is excluded from the top-25 shortlist passed to Bedrock. This avoids the noise and bounds problems of negative weight subtraction.

 **Profile data threshold:**
 The content-based scoring profile does not become reliable until approximately 10–15 liked games exist, where top mechanics are reinforced by multiple independent sources. With fewer than 5 liked games the profile is dominated by 1-2 individual titles and recommendations are essentially "games like X." The onboarding flow must therefore collect at least **5 genuine ratings** (thumbs up or down — not skips) before enabling the "Get Recommendations" action. A progress indicator should communicate this requirement to the user.

 **Adaptive round selection:**
 Round 1 shows 5-6 fixed seed games spanning diverse mechanic clusters. Round 2 selects 4-5 follow-up games based on Round 1 responses — steering toward unexplored mechanic territory to maximise profile diversity, not just confirming existing preferences. This gives richer signal from 10 questions than a static fixed list would.

 **Skip semantics:**
 "Skip" is labelled **"Haven't played it"** in the UI to reduce rating anxiety and make the intent unambiguous. Skipped games are omitted from the inline profile entirely — they are not assigned a neutral rating.

 **Inline profile via request body:**
 No new API endpoint is needed. The existing `POST /recommendations` request accepts an optional `inline_profile` body field containing a list of `{id, rating}` objects. When present, the Lambda skips the S3 parquet lookup entirely and constructs the user dataframe from the inline payload. Inline-profile recommendations are **not cached** in S3 (the cache key logic is skipped), since the inputs are transient and differ per session.

 **State persistence:**
 Onboarding ratings are saved to `localStorage` immediately as the user rates each game, so a page refresh does not lose progress. If the user is authenticated via Cognito, completed onboarding ratings are additionally written to the DynamoDB preferences table so they survive across devices. If the user subsequently provides a real BGG username, the scraped profile takes precedence and the onboarding profile is discarded.

 ### Tasks

 #### Seed Catalog & Adaptive Selection
 - [ ] **Curated Seed Catalog:** Curate 14-16 widely recognised board games across maximally distinct mechanic clusters (e.g. Gloomhaven, Catan, Codenames, Ticket to Ride, Pandemic, 7 Wonders, Azul, Wingspan, Dominion, Scythe, Coup, Dixit, Agricola, Root). Each game should represent a distinct mechanic cluster so that any 10-game subset provides broad coverage.
 - [ ] **Round 1 Fixed Set:** Select 5-6 games from the seed catalog as the fixed Round 1 set, maximising mechanic diversity.
 - [ ] **Round 2 Adaptive Selection:** After Round 1, compute which mechanic clusters are unrepresented in the user's responses and select 4-5 follow-up games from the seed catalog that explore those clusters. Fall back to random selection from the remaining catalog if all clusters are represented.

 #### Onboarding UI
 - [ ] **Card-by-Card Rating Wizard:** Implement a full-screen card carousel showing one game at a time with its cover art, name, and mechanic tags. Buttons: 👍 Thumbs Up / 👎 Thumbs Down / Haven't played it.
 - [ ] **Progress Indicator:** Display a "X of 5 ratings needed" progress bar that unlocks the "Get Recommendations" button once ≥5 genuine (non-skip) ratings are collected.
 - [ ] **localStorage Persistence:** Save each rating to `localStorage` as it is made. Pre-populate the wizard state from `localStorage` on load so a page refresh does not lose progress.
 - [ ] **Cognito Integration:** If the user is authenticated, write completed onboarding ratings to the DynamoDB preferences table on wizard completion.

 #### Backend Changes
 - [ ] **Inline Profile Support:** Update `bgg_recommender.py` to accept an optional `inline_profile` field in the JSON request body. When present, construct the user dataframe directly from the payload (list of `{id, rating}` objects) and skip the S3 parquet lookup and recommendation cache read/write steps entirely.
 - [ ] **Dislike Hard Exclusion:** After candidate scoring, identify the primary mechanics (top 1-2 by weight contribution) of each disliked game in the inline profile. Remove from the top-25 shortlist any candidate whose mechanic set is dominated by those dislike mechanics and shares no overlap with liked mechanics.
 - [ ] **Inline Profile Mapping:** Map onboarding responses to ratings: Thumbs Up → 9.0, Thumbs Down → 3.0. Skipped games are omitted from the payload entirely.

 #### Testing
 - [ ] **Backend Unit Tests:** Verify the recommendation generator executes correctly when provided with an inline profile payload, including edge cases: all thumbs up, mixed ratings, minimum 5-rating payload, and empty dislike exclusion list.
 - [ ] **Dislike Exclusion Tests:** Verify that candidates dominated by disliked mechanics are correctly excluded from the shortlist passed to Bedrock.

---

## Milestone 21: Hybrid Collaborative Filtering via LightFM (Pickled Model)

### Objective
Train a LightFM hybrid collaborative filtering model using both explicit ratings and implicit item features (mechanics, categories). Serialize the model to S3 to enable matrix factorization recommendations in the serverless Lambda backend, effectively solving the cold-start problem by projecting user tastes into the latent feature space.

### Tasks
- [ ] Configure `ml_engine` Docker container to pull `users_combined.parquet` and `catalog.parquet` for weekly offline training.
- [ ] Train LightFM model with $k=30$ latent components, incorporating mechanics and categories as item features.
- [ ] Serialize the trained LightFM model, dataset mapping, and feature dicts to `.pkl` files and upload to S3.
- [ ] Update serving Lambda backend to download the LightFM artifacts on warmup (approx. 40MB memory footprint).
- [ ] Implement scoring logic in Lambda: `model.predict(user_id)` for existing users, and ALS folding-in/feature projection for brand new users based on their selected mechanics/categories.
- [ ] Incorporate the collaborative ratings prediction into a hybrid composite scoring loop alongside heuristic weights, allowing potential UI "taste slider" tuning.

---

## Milestone 23: Affinity Refinement (TF-IDF)

### Objective
Address user feedback regarding skewed recommendations caused by overly generic mechanics.

### Design Notes
- **Mechanic Weighting Refinement:** Generic tags like "Solo / Solitaire Game" or "Card Game" carry disproportionate weight and skew affinities. We will implement an Inverse Document Frequency (IDF) style down-weighting for ubiquitous tags.

### Architecture Decisions
- **TF-IDF Weighting:** We'll load the `mechanic_frequencies.json` into the scoring pipeline and apply a logarithmic penalty to mechanics based on how frequently they appear in the catalog.

### Tasks
- [ ] **Milestone 23: TF-IDF Affinity Refinement**. Load `mechanic_frequencies.json` and apply IDF-based down-weighting to mechanics in affinity scores.

---

## Milestone 25: Offline Relationship-Based Deduplication

### Objective
Prevent variants, expansions, or duplicate editions of the same game family/series (e.g. *Unmatched* or *The Lord of the Rings* trick-taking games) from cluttering recommendations before candidate games are passed to the Bedrock LLM, utilizing structured BGG relationships while keeping different thematic implementations separate.

### Design Notes
- **Scraped Relationships**: Instead of resolving duplicates via real-time BGG API requests, the game data scraper will parse and store `boardgamefamily`, `boardgameimplementation`, `boardgameintegration`, and `boardgameexpansion` relationship link lists offline.
- **Offline Filtering**: The recommender Lambda will inspect candidate relationship fields offline and check for overlap with already-selected games to filter out duplicate system variants.

### Architecture Decisions
- **Schema Updates**: The game data scraper and compactor will be updated to include relationship array fields in their Parquet schemas.

### Tasks
- [ ] **Game Data Scraper Update:** Update PyArrow schema and XML parsing in `bgg_game_data_scraper.py` to extract expansion, implementation, integration, and family links.
- [ ] **Compactor Schema Alignment:** Add the new relationship columns to the Target Schema in `combine_raw_to_single_file.py`.
- [ ] **Recommender Offline Deduplication:** Update `bgg_recommender.py` to filter candidates offline based on overlaps in their structured relationship keys.
- [ ] **Unit Testing:** Implement a new test suite verifying relationship-based candidate deduplication.


---

## Milestone 27: Interactive User Profile Dashboard & Playground

### Objective
Create a user profile page accessible to logged-in users that showcases rich stats, taste profiles, and collection metrics. Incorporate a layout playground allowing users to toggle between different visualization profiles (Overview, Deep Dive, and Rating Analytics) to explore layout options.

### Design Notes
- **Profile Header Dropdown:** Update `header.html` to convert the logged-in user badge into an interactive dropdown containing links to "View Profile" and "Log Out".
- **Glassmorphic Multi-View Dashboard:** Design a sleek profile page with glassmorphism panels. Provide a tab/switch at the top to toggle between three visual presets:
  1. *Overview Dashboard:* High-level KPI cards (Total Games, Complexity Avg, etc.) and Chart.js visualizations for Player Count and Complexity Weight distributions.
  2. *Deep Dive Metrics:* Detailed charts covering game duration breakdown, year published distributions, and category counts.
  3. *Rating Analytics:* Comparison scatter/bar plots for User Ratings vs. BGG Ratings, average deviation, and listings of favorite designers and publishers.
- **Skeletal Shimmer Loading:** Implement CSS/HTML placeholder templates that animate/shimmer during background data fetch processes.

### Architecture Decisions
- **Unified Profile Routing:** Create a new endpoint `/profile/index.html` referencing Jekyll layouts and configuration.
- **Cognito & API Sync:** Fetch `bgg_username` from backend preferences and pull user XML collection and pre-computed `/profile` statistics from the taste analytics API on page load. Fall back to client-side taste profiling in case of network/fetch issues.

### Tasks
- [ ] **Header Dropdown Component:** Modify `site_ui/_includes/header.html` to replace the simple text link with a custom hover/click CSS dropdown for logged-in users.
- [ ] **Profile Page Creation:** Add `site_ui/profile/index.html` with basic layout framework and sidebar/header integration.
- [ ] **Multi-View Control & Switcher:** Implement layout switching logic to toggle between Overview, Deep Dive, and Rating Analytics layouts.
- [ ] **Chart.js Implementations:**
  - [ ] Add player count and complexity charts to the Overview dashboard.
  - [ ] Add duration, year, and category charts to the Deep Dive dashboard.
  - [ ] Add ratings scatter/bar plot and creator listings to the Rating Analytics dashboard.
- [ ] **Skeletal Shimmer Loading UI:** Add skeleton layouts that display during asynchronous API collection loading.
- [ ] **Offline Fallbacks & Integration:** Connect Cognito session authentication checks, sync pref loading, and fall back to local parsing for profiles missing computed backend statistics.

---

## Completed Milestones

* **Milestone 1: Crawler & Data Pipeline Verification** (AWS S3 combined catalog downloads, custom Parquet schema mapping)
* **Milestone 2: Scraper Resilience, Concurrency Limiting, & API Back-off** (SQS rate limiting, exponential backoff/jitter)
* **Milestone 3: Serving Caching & API Performance Optimization** (S3 and client localStorage caching)
* **Milestone 4: Recommender Enhancements & Dynamic Personalization UI** (weights, BGG hotness tuning, dynamic parameters)
* **Milestone 5: Playgroup Organizer & Game Night Planner Page** (attendee filtering, group collection merging)
* **Milestone 6: Rich Cards & CDN-Cached Image Rendering** (metadata display, visual image cards)
* **Milestone 7: Unit Testing & CI/CD Verification** (pytest, GitHub Actions workflows)
* **Milestone 8: Database Reprocessing & Full Catalog Scrape Execution** (scraper reprocessing, serverless python compactor Lambda)
* **Milestone 10: Mobile UI Optimization & Responsive Navigation Menu** (responsive layouts, blurred backdrop mobile drawer)
* **Milestone 11: Taste Analytics Backend** (Event-driven pipeline using SQS and Lambda to pre-compute user taste profiles in JSON format)
* **Milestone 12: Production Observability, Rate Limiting, & Cost Protection** (API limits, structured logging, alarms)
* **Milestone 13: Serverless Cost Optimization & Glue Crawler Bypass** (Python pandas/pyarrow compaction Lambda, bypass Athena)
* **Milestone 14: Recommender Personalization via Duration & Complexity Weighting** (Pacing/complexity soft-weighting, Bedrock justifications, frontend selectors)
* **Milestone 15: User Authentication & Profile Persistence** (Amazon Cognito integration, DynamoDB preferences/playgroups synchronization, custom glassmorphism modal UI)
* **Milestone 16: Unified Analytics & Taste Profile UI** (Cohesive dashboard experience with glassmorphism layout, dynamic Chart.js visualizations for individual/playgroup collection statistics and taste profiles)
* **Milestone 18: Varied & Engaging AI Recommendation Explanations** (Prompt example removal, explicit 7-angle rotation instruction, hard opener uniqueness constraint, elevated temperature, Converse system prompt, test coverage)
* **Milestone 19: BGG GeekPreview Convention Recommendations** (Active previews metadata configuration, Lambda daily synchronization of preview game IDs, recommender filter, in-memory TTL caching, frontend convention dropdown, and convention badges)
* **Milestone 20: Cognito Verification Email Delivery Setup** (SES identity created, IAM policies granted, custom HTML email templates added to Terraform)
* **Milestone 22: LLM Prompt Grounding & Deduplication** (Injected catalog mechanics into Bedrock prompt to eliminate hallucination, and added instructions to deduplicate variants)
* **Milestone 24: Responsive Grid UI** (CSS container widths updated to prevent unnecessary horizontal scrolling)
* **Milestone 26: UI Redesign & Polish** (Standardized grid wrapper alignment, full-width responsive BGG collection grid/analytics table, symmetric AI form layout, realigned playgroup panel with loading animations, glassmorphism visual accents)
