# Boardgame Recommender - Project Roadmap

This document outlines the next steps and active architecture enhancements for the Boardgame Recommender project.

---

## Active Initiatives: Board Game Cafe & Bar Edition

For comprehensive milestones, user journeys, and technical architecture specifications for the **Board Game Cafe & Bar Edition**, see [cafe_roadmap.md](file:///d:/Git/Boardgame-Recommender/cafe_roadmap.md) and [docs/cafe_edition_design.md](file:///d:/Git/Boardgame-Recommender/docs/cafe_edition_design.md).

- **Milestone C1: Self-Service Cafe Onboarding & Dynamic Venue Registry** (Completed)
- **Milestone C2: Cafe Inventory Ingestion & On-Demand Sync** (Completed)
- **Milestone C3: Self-Service Cafe Management Portal & Venue Dashboard** (Completed)
- **Milestone C4: Cafe-Scoped Candidate Pool & 30-Second Table Vibe Engine** (Completed)
- **Milestone C5: Mobile-First Cafe Patron Portal & Vibe Check UI** (Completed)
- **Milestone C6: "Watch It Played" Rules Video & Media Integration** (Completed)
- **Milestone C7: Table QR Code Generator & Real-Time Table Voting** (Completed)
- **Next Up: Milestone C8: Cafe Floor Staff Portal, Shelf Locations & Manual Catalog Overrides** (See [cafe_roadmap.md](file:///d:/Git/Boardgame-Recommender/cafe_roadmap.md#L217))

---

## Milestone 31: Similar Games API Endpoint

### Objective
Add a content-based "Similar Games" endpoint to the recommender Lambda that returns the top 10 most similar games to a given BGG game ID by mechanic and category Jaccard overlap, without requiring a user profile.

### Design Notes
- **Pure Content Similarity:** This is a catalog-only lookup — no user profile, no Bedrock call. Given a `game_id`, load the catalog, compute Jaccard similarity of the target game's mechanics and categories against all other games, and return the top 10 results with metadata.
- **Use Case:** Powers "More Like This" buttons on recommendation cards and collection rows. Could also be exposed as a standalone tool for users who want to find alternatives to a specific game.

### Architecture Decisions
- **New Route:** Add a `GET /similar?game_id=XXXXX` path to the existing Lambda handler routing in `bgg_recommender.py`, handled by a new `_handle_similar(query_params)` function.
- **Scoring:** Jaccard similarity = |intersection| / |union| for both mechanics and categories, combined with configurable weights (default 60% mechanics, 40% categories). Optionally boost games with matching designers.
- **Caching:** Cache results in S3 with a 7-day TTL keyed by game ID, since catalog data changes infrequently.

### Tasks
- [ ] **Similar Games Scoring Function:** Implement `find_similar_games(game_id, catalog_df, top_n=10)` in `scoring.py` using Jaccard similarity on mechanics and categories.
- [ ] **Lambda Route Handler:** Add `_handle_similar(query_params)` to `bgg_recommender.py` that validates the `game_id` param, loads the catalog, calls the scoring function, and returns results with game metadata.
- [ ] **Lambda Handler Routing:** Update `lambda_handler` to route `/similar` paths to `_handle_similar`.
- [ ] **API Gateway Route:** Add a `/similar` route in the API Gateway Terraform configuration.
- [ ] **S3 Response Caching:** Cache similar-games results in S3 (`data/similar_cache/{game_id}.json`) with a 7-day TTL.
- [ ] **Unit Tests:** Test Jaccard similarity computation, edge cases (unknown game ID, game with no mechanics), and cache hit/miss paths.

---


## Milestone 46: Game Score Inspector

### Objective
Add a lightweight, unobtrusive "Score My Game" tool to the recommender page that lets a user enter a BGG game ID or name and see exactly how that game scored against their taste profile — including per-dimension similarity breakdowns and which filter (if any) eliminated it from the candidate pool.

### Design Notes
- **Use Case:** Users frequently wonder "Why didn't it recommend Gloomhaven?" or "How close was Brass: Birmingham to making the list?" This tool provides scoring transparency without requiring users to understand the algorithm — they enter a game name and see a simple breakdown.
- **UI Principle:** This is a **power-user debugging tool**, not a primary workflow. It should be completely unobtrusive: a small "🔍 Score a game" link below the recommendation results that expands an inline panel or opens a compact modal. It must never distract from the main recommendation flow.
- **Scope:** This is a read-only diagnostic. It does not modify recommendations, preferences, or any stored data. The backend computes the score on-demand against the user's current taste profile and returns it.

### Architecture Decisions
- **New Route:** Add a `GET /score?username=XXX&game_id=YYYYY` path to the existing Lambda handler routing in `bgg_recommender.py`, handled by a new `_handle_score(query_params)` function. Reuses the existing taste profile computation and scoring logic — no new algorithms needed.
- **Response Format:** Return a JSON object with: `{ game: {name, id, mechanics, categories, ...}, scores: {mechanic_sim, category_sim, popularity, hotness, complexity_sim, designer_sim, publisher_sim, composite}, filter_status: "included" | {excluded_by: "ownership|player_count|year_range|rating_threshold|not_in_catalog"} }`.
- **No Caching:** Score inspector results are not cached. They are fast single-game computations (no Bedrock call) that should reflect the user's current profile state.

### Tasks
- [ ] **Score Function:** Implement `score_single_game(game_id, catalog_df, mech_weights, cat_weights, user_designers, user_publishers, complexity_weights, hotness_scores, query_params, weights)` in `scoring.py` that returns a dict of per-dimension similarity scores and the composite score for a single game. Reuse the existing scoring math from `score_candidates()` extracted into a shared helper.
- [ ] **Filter Status Check:** Implement `check_filter_status(game_id, catalog_df, owned_ids, rated_ids, query_params)` in `scoring.py` that returns whether the game was excluded by any active filter and which filter removed it.
- [ ] **Lambda Route Handler:** Add `_handle_score(query_params)` to `bgg_recommender.py` that validates the `game_id` and `username` params, loads the catalog and user profile, computes the taste profile, scores the single game, checks filter status, and returns the combined result.
- [ ] **Lambda Handler Routing:** Update `lambda_handler` to route `/score` paths to `_handle_score`.
- [ ] **API Gateway Route:** Add a `GET /score` route in the API Gateway Terraform configuration, pointing to the existing recommender Lambda integration.
- [ ] **Frontend Inspector UI:** Add a "🔍 Score a game" collapsible link below `#recommendations-results` in `site_ui/recommender/index.html`. When expanded, show a text input for game name/ID with a "Check Score" button. On submit, call `GET /score` and render a compact breakdown card showing each score dimension as a labelled bar (0–100%), the composite score, and the filter status. Style consistently with the existing glassmorphism card system.
- [ ] **Unit Tests:** Test single-game scoring against a known taste profile (verify per-dimension math matches `score_candidates` output), filter status detection for each exclusion reason, and edge cases (game not in catalog, invalid game ID).



---

## Archived / Deferred Milestones

The following milestones have been evaluated and archived/deferred based on architectural complexity, high operational maintenance, or being superseded by simpler, more cost-effective solutions:

### Archived Milestone 35: Gamefound Crowdfunding Recommendations
* **Status:** Archived / Deprioritized.
* **Rationale:** Crowdfunding campaigns are temporary and time-bound. The Gamefound public API does not provide BGG IDs, requiring brittle fuzzy string title resolution with high false-positive and false-negative rates. Convention preview tracking (Milestone 19) already fulfills user interest in upcoming titles with significantly higher data reliability.

### Archived Milestone 42: WebSocket Recommendation Streaming
* **Status:** Archived / Deferred.
* **Rationale:** Building and operating a stateful API Gateway WebSocket API with DynamoDB connection tracking (`bgg-ws-connections`) introduces substantial operational complexity. Following Milestone 44's latency optimizations (parallel S3 downloads, reduced Bedrock token limits), cold recommendation response times were reduced to 2–4 seconds and repeat queries serve from cache in <300ms. If streaming is ever pursued, HTTP Lambda Response Streaming or Server-Sent Events (SSE) avoids stateful connection management entirely.

### Archived Milestone 43: Collaborative Filtering Hybrid Model
* **Status:** Archived / Superseded.
* **Rationale:** The experimental `ml_engine/` was officially retired and moved to `deprecated/` in Milestone 38. Training and maintaining a full collaborative filtering model across 139,000 games and sparse user ratings introduces high infrastructure complexity and cost (SageMaker jobs, large serialized artifacts, model staleness). Candidate scoring homogenization was solved serverlessly in Milestone 61 (true cosine similarity and continuous Gaussian complexity decay) and Milestone 62 (TF-IDF catalog base-rate discounting), rendering CF unnecessary for the platform's core goals.

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
* **Milestone 27: Interactive User Profile Dashboard & Playground** (Cognito profile syncing, Overview, Deep Dive, and Rating Analytics layouts, hover/click user header dropdown, and grouped rating distribution bar charts)
* **Milestone 28: Shared CSS Design System & JS Utilities Extraction** (Extracted shared CSS variables, layout configurations, component classes, and Cognito Auth/fetch wrappers into centralized files)
* **Milestone 29: Dark Mode Toggle** (User-togglable dark mode, custom property variables, transition animations, localStorage persistence, blocking pre-render script, page styling audits)
* **Milestone 30: Skeleton Loading States** (Replaced spinner-based loading indicators with animated shimmering skeleton placeholder tables and cards in Recommender, Collection Browser, and Playgroup Organizer)
* **Milestone 32: API Gateway Response Compression** (Enabled native gzip response compression on API Gateway and exposed the Content-Encoding header in CORS configurations)
* **Milestone 34: Empty States, Onboarding Guidance & Cold-Start Rating Flow** (Polished empty state preview overlay, Gamer Quick Taste Test with Round 2 adaptive selection, Casual Personality Test with 7 playstyle questions, S3-bypass inline profile/weights POST submissions, and mechanic-based dislike exclusions)
* **Milestone 36: Security Hardening & CORS Fixes** (Removed wildcard Lambda CORS headers, added API Gateway POST preflights, added regex username validation, moved Cognito Client/Pool IDs to GitHub secrets)
* **Milestone 37: DynamoDB Preferences Safety & Backend DRY Refactor** (Migrated preferences handler POST to table.update_item, centralized weight parsing helper in cache_utils.py, simplified client mock patching with dynamic __getattr__ module routing)
* **Milestone 38: Repository Hygiene & Code Quality** (Removed deprecated bgg_raw_to_compressed/ and ml_engine/ directories, extracted recommender index.html styles/scripts to external files, removed inert moved blocks from main.tf, and hardened test conftest AWS mock keys)
* **Milestone 39: Test Coverage Expansion** (S3 caching layer unit tests, Bedrock narration pipeline unit tests, Vitest + JSDOM frontend tests, CI path trigger fix)
* **Milestone 40: Groups Page Redesign — Tabs & Per-Member Affinity** (Structured tabs layout, per-member taste alignment bar charts, dynamic color-coding, 100% max clamping, and backend Lambda scoring helper extraction)
* **Milestone 41: Shareable Top 10 Recommendation Graphic & Image Export** (Implemented HTML5 Canvas generator module graphic_export.js for generating 1200x675 high-res social graphics of top 10 recommended games without AI text, added Export Image modal with live preview, 1-click Download PNG, Clipboard copy, and mobile Web Share API integration)
* **Milestone 44: Recommender Latency Optimization** (Parallelized S3 profile checks, parquet downloads, and taste profile loading with ThreadPoolExecutor, Bedrock maxTokens reduced to 800 with 15-word concise narration constraint, removed redundant catalog copies, and cached catalog data conversions)
* **Milestone 45: Recommendation Diversity Guard** (Deterministic post-scoring diversification pass to prevent mechanic and category clustering in Bedrock shortlists)
* **Milestone 47: Release Polish (SEO, Favicon & Social Sharing)** (Registered jekyll-seo-tag and jekyll-sitemap, linked generated favicon and apple touch icons, audited page metadata, configured default OpenGraph/Twitter sharing cards, and added a custom glassmorphic 404 landing page)
* **Milestone 48: Collection Browser Image Fitting** (Updated collection browser game images to `object-fit: contain` with customized dark/light mode gradient containers to ensure aspect-ratio-aware fitting without cropping)
* **Milestone 49: Mobile UI Polish Pass** (Comprehensive responsiveness audit, WCAG 2.1 44px touch targets, mobile wizard modal & taste test carousel, adaptive filters and affinity bars, table overflow protection, and responsive layouts across all viewports from 320px to 768px)
* **Milestone 50: Local Development Environment** (Gitignored _config.local.yml and .env.local overrides, gen_local_config.py generator script, comprehensive LOCAL_DEVELOPMENT.md guide, and enhanced offline mock API handlers for /profile, /groups, and /preferences)
* **Milestone 51: Taste Test Image Loading Fix** (Replaced broken full-sized BGG CDN images with verified smaller thumbnail URLs in the seed catalog array, and added a fallback placeholder handler to the HTML markup)
* **Milestone 52: New User AI Narration Context** (Added prompt branching in narration.py for Casual Personality Test and Quick Taste Test, forwarded personality quiz answers from frontend to backend, tuned punchy/direct 1-sentence explanations aiming for 12–15 words, and raised generation maxTokens to 1,200 at 0.6 temperature)
* **Milestone 53: Recommendation Card Redesign** (Explored visual mockup options, implemented Option A 2-column desktop grid for ≥1024px monitors in design-system.css, updated card padding, flex alignment, member affinity bar tracks, and aligned skeleton loading placeholders)
* **Milestone 54: Scoring Pipeline Corrections** (Projected true cosine similarity, dislike threshold boundary lowered to 6.5, group re-computation deduplication, BGG_TESTING env var test bypass, and sum-based complexity weighting)
* **Milestone 55: Wizard Write-In Game Search & Expanded Seed Catalog** (50-game auto-generated SEED_CATALOG, 9 adaptive Round 2 picks, static minified 5,000-game autocomplete database, debounced vanilla JS search with keyboard navigation, 3 write-in slots in Taste Test & Personality Test with 9.0 rating assignment)
* **Milestone 56: Monthly Stats Refresh for Recent Board Games** (Added `recent` mode to `bgg_game_scraper.py` with `--window` support, EventBridge monthly schedule `cron(0 3 1 * ? *)` with container environment overrides, SQS batch queuing of recent game IDs `[start_id - 2500, start_id]`)
* **Milestone 57: Async Game Night Voting & Veto Session** (Defined bgg-game-night-sessions DynamoDB table with GSI and TTL, built sessions.py consensus engine with +2/+1/-99 veto scoring and tie-breaking, created standalone vote/index.html voting page with live countdown timer, and added host poll modal & Past Polls history tab on groups/index.html)
* **Milestone 58: Collection Browser Loading State & Skeleton Redesign** (Maintained visible persistent filter sidebar in loading state to eliminate layout jumping, rendered 8-card shimmering card grid skeleton matching default Card View)
* **Milestone 59: User Profile Skeleton Animation & Viewport Alignment Fix** (Fixed @keyframes shimmer in design-system.css and profile/index.html to animate background-position instead of transform: translateX, eliminating offscreen lateral drift during profile dashboard load)
* **Milestone 60: Playgroup Organizer Clean Modern Redesign** (Redesigned planner view with interactive tactile avatar chips, initials badges, emerald active indicators, inline attendance header counter with Select All / Clear actions, streamlined group header with member count pill and Edit/Delete action links, balanced two-column glassmorphic filter controls, and prominent primary recommendation button)
* **Milestone 61: Content-Based Scoring Normalization & Popularity De-biasing** (Implemented true cosine similarity dividing tag dot products by candidate vector norms $\sqrt{|\text{cand\_tags}|}$, rebalanced default weights to w_pop=0.20, w_mech=0.60, w_cat=0.40, w_des=0.35, w_comp=0.35 in cache_utils.py and UI presets, replaced coarse complexity buckets with continuous Gaussian distance decay centered on user mean complexity with $\sigma=0.75$, upgraded diversify_candidates() to track decayed secondary tags, and verified with comprehensive unit test suite)
* **Milestone 62: Taste Profile TF-IDF & Catalog Base-Rate Discounting** (Calculated catalog document frequencies across 139k BGG games to derive smoothed IDF factors $\ln(1 + N_{\text{catalog}} / N_f)$ in catalog_feature_frequencies.json, implemented TF-IDF discounting in bgg_taste_analytics.py and scoring.py for offline/inline parity, elevated distinctive tags over ubiquitous baseline tags, updated taste profile schema with idf_applied: true and user_mean_complexity, and added unit tests validating distinctive tag elevation, backward compatibility, and profile parity)
* **Milestone 63: User Password Reset & Recovery Flow** (Enabled self-service client-side Cognito password recovery via ForgotPassword and ConfirmForgotPassword in utils.js, designed multi-step glassmorphic recovery views in default.html and header.html, enforced password complexity policies with real-time hints and mapped Cognito error codes to friendly messages, and added comprehensive Vitest test coverage)
* **Milestone C1: Self-Service Cafe Onboarding & Dynamic Venue Registry** (DynamoDB `bgg-cafes` table, BGG collection validation endpoint, multi-step onboarding wizard at `site_ui/cafe/onboard.html`, and automated printable QR table tent generation)
* **Milestone C2: Cafe Inventory Ingestion & On-Demand Sync** (Scraper cafe mode handler for `own=1`, on-demand `POST /cafe/sync` SQS dispatch with recommendation cache invalidation, EventBridge weekly automated sync rule, and unit test coverage)
* **Milestone C3: Self-Service Cafe Management Portal & Venue Dashboard** (Dedicated venue management portal at `site_ui/cafe/manage.html`, `GET /cafe/my-cafes` GSI query handler, `POST /cafe/update` venue editor with DynamoDB and S3 synchronization, API Gateway Cognito authorizer routes, printable double-sided folded table tent batch generator, and profile/header navigation integration)
* **Milestone C4: Cafe-Scoped Candidate Pool & 30-Second Table Vibe Engine** (Hard cafe inventory candidate masking by cafe BGG username, Gaussian complexity and normalized vibe profile weighting vectors, Nova Micro sommelier prompt with rules teach time and shelf location, S3 recommendation caching with 7-day TTL, and unit test coverage)
* **Milestone C5: Mobile-First Cafe Patron Portal & Vibe Check UI** (Mobile-first responsive glassmorphic patron interface at `site_ui/cafe/index.html` with `cafe.css` and `cafe.js`, co-branded venue header with table badge and Wi-Fi credential copy, tactile 3-tap vibe quiz for player count, session duration, and vibe cards, collapsible BGG hobbyist bypass, mobile game cards with shelf location, teach time, AI sommelier quote, rules video links, empty state relaxation chips, and Vitest suite)
* **Milestone C6: "Watch It Played" Rules Video & Media Integration** (Curated video link ingestion from BGG API XML `/thing?videos=1` in `bgg_game_data_scraper`, resolution of `rules_video_url` in recommender payload, accessible responsive in-app video modal in `site_ui/cafe/index.html` with YouTube nocookie embed and fallback search links, and rules teach time badges adjacent to video triggers)
* **Milestone C7: Table QR Code Generator & Real-Time Table Voting** (`scripts/generate_cafe_table_qrs.py` vector SVG & printable HTML sheet generator with 180° inverted folding top panel, `POST /cafe/vote/start` single-tap session auto-creation with group naming `{Cafe} - Table {N}`, integration with `bgg-game-night-sessions` DynamoDB table and `sessions.py` consensus scoring engine, and live table voting cards)



