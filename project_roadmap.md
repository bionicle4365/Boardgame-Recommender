# Boardgame Recommender - Project Roadmap

This document outlines the next steps and active architecture enhancements for the Boardgame Recommender project.

---

## Milestone 44: Progressive Web App & Offline Support

### Objective
Make the Jekyll site installable as a mobile app with offline caching, enabling users to browse cached recommendations and collection data without connectivity — particularly useful at board game stores and conventions.

### Design Notes
- **Use Case:** Board gamers frequently browse recommendations at game stores (deciding what to buy) or conventions (checking recommendations between sessions) where Wi-Fi is spotty or unavailable. Having the last set of recommendations and collection data available offline is genuinely useful.
- **PWA Requirements:** A valid PWA needs a `manifest.json` (app metadata, icons, theme colors), a registered service worker (caching strategy), and HTTPS (already satisfied via GitHub Pages).
- **Caching Strategy:** Cache-first for static assets (HTML, CSS, JS, images). Network-first with stale fallback for API responses (recommendations, collection data). The service worker stores the last successful API response for each cached endpoint in the Cache API.

### Architecture Decisions
- **Service Worker Scope:** Register the service worker at the site root (`/Boardgame-Recommender/sw.js`). Cache the app shell (all HTML pages, `design-system.css`, `utils.js`, and page-specific JS) on install. Intercept API fetch requests and cache successful responses for offline fallback.
- **Manifest:** Define a `manifest.json` with app name, short name, theme color matching the glassmorphism palette, background color, start URL, display mode `standalone`, and generated icons at 192px and 512px.
- **Install Prompt:** Show a subtle "Install App" banner on the first visit (dismissible, tracked via `localStorage`). Don't interrupt the user flow — the banner appears below the header, not as a modal.

### Tasks
- [ ] **Web Manifest:** Create `site_ui/manifest.json` with app metadata, theme colors aligned to the existing glassmorphism palette, and icon references.
- [ ] **App Icons:** Generate PWA icons at 192x192 and 512x512 sizes in the site assets directory.
- [ ] **Service Worker:** Create `site_ui/sw.js` implementing cache-first for static assets and network-first-with-stale-fallback for API responses. Include cache versioning for cache-busting on deploys.
- [ ] **Service Worker Registration:** Add service worker registration script to the default Jekyll layout (`_layouts/default.html`) with feature detection fallback.
- [ ] **Install Prompt UI:** Add a dismissible "Install App" banner to the site header area, shown only when the `beforeinstallprompt` event fires. Track dismissal in `localStorage`.
- [ ] **Offline Indicator:** When the service worker detects no connectivity, display a subtle "Offline — showing cached data" banner at the top of the page.
- [ ] **Verification:** Test install flow on Android Chrome and iOS Safari. Verify offline browsing shows cached recommendations and collection data. Verify the app updates correctly when new content is deployed.

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

## Milestone 34: Empty States, Onboarding Guidance & Cold-Start Rating Flow

### Objective
Replace blank/empty page states with visually polished onboarding guidance and provide a seamless recommendation flow for users without a BoardGameGeek profile (or with insufficient data) via a two-round adaptive game rating wizard that builds a temporary inline taste profile.

### Design Notes

**Empty States:**
- **Current State:** Pages show no content until a BGG username is entered or the user is logged in. First-time visitors see empty containers with no context.
- **Visual Approach:** Each empty state should be minimal and tasteful — a short headline, 1-2 sentence description, and a single clear CTA. Avoid heavy illustration or multi-step walkthroughs. The glassmorphism card style already established in the UI provides a natural container.
- **Scope Caution:** Empty states must not feel intrusive or tutorial-heavy. They should disappear permanently once the user has engaged with the feature (tracked via `localStorage` flag).

**Cold-Start Onboarding (BGG Profile Bypass):**
- **Why only positive ratings build the weight profile (and what we do about it):** The recommender's scoring weights are built exclusively from liked games (rating >= 7.0). Disliked games (rating 3.0) are excluded from the weight-building step — they do not penalise mechanics in candidate scoring. For a full BGG profile (15+ liked games), positive signal alone is dense enough that this is not a significant limitation. For the cold-start case (3-8 liked games), disliked games represent meaningful signal that must not be silently discarded. The solution is a **hard candidate exclusion** rather than negative weight subtraction: after scoring, any candidate game whose primary mechanics are dominated by mechanics from disliked games (with no overlap with liked mechanics) is excluded from the top-25 shortlist passed to Bedrock.
- **Profile data threshold:** The content-based scoring profile does not become reliable until approximately 10–15 liked games exist. The onboarding flow must collect at least **5 genuine ratings** (thumbs up or down — not skips) before enabling the "Get Recommendations" action. A progress indicator should communicate this requirement to the user.
- **Adaptive round selection:** Round 1 shows 5-6 fixed seed games spanning diverse mechanic clusters. Round 2 selects 4-5 follow-up games based on Round 1 responses — steering toward unexplored mechanic territory to maximise profile diversity.
- **Skip semantics:** "Skip" is labelled **"Haven't played it"** in the UI. Skipped games are omitted from the inline profile entirely — they are not assigned a neutral rating.
- **Inline profile via request body:** The existing `POST /recommendations` request accepts an optional `inline_profile` body field containing a list of `{id, rating}` objects. When present, the Lambda skips the S3 parquet lookup entirely and constructs the user dataframe from the inline payload. Inline-profile recommendations are **not cached** in S3.
- **State persistence:** Onboarding ratings are saved to `localStorage` immediately. If the user is authenticated via Cognito, completed onboarding ratings are additionally written to the DynamoDB preferences table. If the user subsequently provides a real BGG username, the scraped profile takes precedence.

### Tasks

#### Empty States
- [ ] **Home Page Empty State:** Add a subtle "Getting Started" card below the feature grid for first-time visitors (no username in `localStorage`) with a brief explanation and a "Enter your BGG username to begin" prompt.
- [ ] **Recommender Empty State:** Show 2-3 blurred/faded example recommendation cards as a visual preview of what results look like, with an overlay CTA to enter a username or start the cold-start onboarding wizard.
- [ ] **Collection Empty State:** Add a brief description card explaining the collection browser with a CTA pointing to the username form.
- [ ] **Profile Empty State:** When not logged in, show a teaser card explaining what the profile dashboard offers with a "Log in to view" CTA.
- [ ] **localStorage Dismissal:** Track `onboarding_dismissed` in `localStorage` so empty states are hidden once the user has engaged.

#### Seed Catalog & Adaptive Selection
- [ ] **Curated Seed Catalog:** Curate 14-16 widely recognised board games across maximally distinct mechanic clusters (e.g. Gloomhaven, Catan, Codenames, Ticket to Ride, Pandemic, 7 Wonders, Azul, Wingspan, Dominion, Scythe, Coup, Dixit, Agricola, Root).
- [ ] **Round 1 Fixed Set:** Select 5-6 games from the seed catalog as the fixed Round 1 set, maximising mechanic diversity.
- [ ] **Round 2 Adaptive Selection:** After Round 1, compute which mechanic clusters are unrepresented in the user's responses and select 4-5 follow-up games from the remaining catalog.

#### Onboarding UI
- [ ] **Card-by-Card Rating Wizard:** Implement a full-screen card carousel showing one game at a time with its cover art, name, and mechanic tags. Buttons: 👍 Thumbs Up / 👎 Thumbs Down / Haven't played it.
- [ ] **Progress Indicator:** Display a "X of 5 ratings needed" progress bar that unlocks the "Get Recommendations" button once ≥5 genuine (non-skip) ratings are collected.
- [ ] **localStorage Persistence:** Save each rating to `localStorage` as it is made. Pre-populate the wizard state from `localStorage` on load so a page refresh does not lose progress.
- [ ] **Cognito Integration:** If the user is authenticated, write completed onboarding ratings to the DynamoDB preferences table on wizard completion.

#### Backend Changes
- [ ] **Inline Profile Support:** Update `bgg_recommender.py` to accept an optional `inline_profile` field in the JSON request body. When present, construct the user dataframe directly from the payload (list of `{id, rating}` objects) and skip the S3 parquet lookup and recommendation cache read/write steps entirely.
- [ ] **Dislike Hard Exclusion:** After candidate scoring, identify the primary mechanics of each disliked game in the inline profile. Remove from the top-25 shortlist any candidate whose mechanic set is dominated by those dislike mechanics and shares no overlap with liked mechanics.
- [ ] **Inline Profile Mapping:** Map onboarding responses to ratings: Thumbs Up → 9.0, Thumbs Down → 3.0. Skipped games are omitted from the payload entirely.

#### Testing
- [ ] **Backend Unit Tests:** Verify the recommendation generator executes correctly when provided with an inline profile payload, including edge cases: all thumbs up, mixed ratings, minimum 5-rating payload, and empty dislike exclusion list.
- [ ] **Dislike Exclusion Tests:** Verify that candidates dominated by disliked mechanics are correctly excluded from the shortlist passed to Bedrock.
- [ ] **Visual Verification:** Verify all empty states look polished on desktop and mobile, and disappear correctly after engagement.

---

## Milestone 41: Shareable Recommendation Links

### Objective
Enable users to generate a unique shareable URL for their recommendation results that others can view without logging in, driving organic discovery and social sharing.

### Design Notes
- **Social Value:** Board gaming is inherently social. Enabling "here are my recommendations — what do you think?" sharing creates organic traffic, enables community discussion, and adds a viral growth mechanism with zero marketing spend.
- **Snapshot Model:** Shared links display a frozen snapshot of the recommendation results at the time of sharing, not a live re-computation. This avoids exposing the user's BGG credentials to viewers and keeps the share page fast (no Lambda cold start).
- **Privacy:** The shared page shows recommendation results only — game names, reasons, and metadata. It does not expose the sharer's BGG username, collection, taste profile, or weight configuration.

### Architecture Decisions
- **Storage:** Store recommendation snapshots in DynamoDB (new `bgg-shared-recommendations` table) keyed by a short hash (8-char base62). Each item contains: `hash_id`, `recommendations` (list of game objects), `created_at`, and `ttl` (DynamoDB TTL attribute, set to 90 days).
- **Share Endpoint:** Add a `POST /share` route (authenticated) that accepts a recommendations payload, generates the hash, stores in DynamoDB, and returns the share URL. Add a `GET /share/{hash}` route (unauthenticated) that retrieves and returns the snapshot.
- **Frontend Flow:** Add a "Share Results" button to the recommendation results area. On click, POST the current recommendations to `/share`, receive the short URL, and display a copy-to-clipboard modal. The share URL renders a read-only recommendation card layout.

### Tasks
- [ ] **DynamoDB Table:** Add a `bgg-shared-recommendations` DynamoDB table to the Terraform `dynamodb` module with `hash_id` as partition key and a TTL attribute on `expires_at`.
- [ ] **Share API Lambda:** Add `POST /share` and `GET /share/{hash_id}` route handlers. `POST` generates an 8-char base62 hash, stores the snapshot, and returns the URL. `GET` retrieves the snapshot by hash.
- [ ] **API Gateway Routes:** Add `/share` POST (authenticated) and GET (unauthenticated) routes in the API Gateway Terraform configuration.
- [ ] **Share Button UI:** Add a "Share Results ↗" button below the recommendation results. On click, call `POST /share` with the current recommendations, display a modal with the shareable URL, and provide a "Copy Link" button.
- [ ] **Shared Results Page:** Create `site_ui/shared/index.html` that reads the hash from the URL query parameter, fetches the snapshot via `GET /share/{hash}`, and renders read-only recommendation cards with a "Get your own recommendations →" CTA.
- [ ] **Unit Tests:** Test hash generation uniqueness, DynamoDB storage/retrieval, TTL expiration behavior, and graceful handling of invalid/expired hash lookups.

---

## Milestone 35: Gamefound Crowdfunding Recommendations

### Objective
Integrate Gamefound's public API to discover actively crowdfunding board games and allow users to receive personalized recommendations for campaigns currently funding, bypassing BoardGameGeek's data lags and paid-widget limitations.

### Design Notes
- **Source Selection**: While Kickstarter lacks a developer API, Gamefound provides a structured, public JSON endpoint (`getActiveCrowdfundingProjects`). 
- **Entity Resolution**: Gamefound projects do not contain BGG IDs. We will map projects to the BGG catalog by querying BGG's search API (`xmlapi2/search?query=NAME&exact=1`) using the project name.
- **Filtering Lag**: To prevent outdated campaigns, we will store campaign start and end dates and cross-reference them against the current system time to guarantee only *active* campaigns are recommended.

### Architecture Decisions
- **Data Sync**: Implement a daily scheduled EventBridge rule triggering a Lambda function (`bgg_gamefound_sync`) that fetches active Gamefound projects, queries BGG's search API to resolve IDs, and writes the mapped JSON list to S3 (`data/gamefound_campaigns.json`).
- **Recommender Integration**: Extend the recommender Lambda (`bgg_recommender.py`) to load the JSON list from S3, enabling users to filter or boost recommendation scoring for games that are actively crowdfunding.
- **Frontend UI**: Add a "Crowdfunding Only" filter to the recommender parameters on the site, and display a "Crowdfunding" badge on recommendation cards with a direct link to the Gamefound campaign page.

### Tasks
- [ ] **Gamefound Sync Lambda**: Implement `bgg_gamefound_sync.py` to query the Gamefound API, resolve project titles to BGG IDs via the BGG XML API2 search endpoint, and write the active campaigns map to S3.
- [ ] **Terraform Infrastructure**: Add Terraform resource definitions for the new Lambda function, IAM policies, and a daily CloudWatch EventBridge Trigger.
- [ ] **Recommender Scoring Update**: Update `bgg_recommender/scoring.py` and `bgg_recommender.py` to load active campaign IDs from S3 and support an `actively_crowdfunding` filter.
- [ ] **Frontend Checkbox & Card Badge**: Add a "Crowdfunding Only" toggle checkbox to `site_ui/recommender/index.html` and render a stylized visual badge linking to the Gamefound project on matching game cards.
- [ ] **Verification**: Add unit tests for Gamefound endpoint parsing, BGG name matching logic (handling title normalization and expansions), and recommender integration.

---

## Milestone 43: Collaborative Filtering Hybrid Model

### Objective
Train a collaborative filtering (CF) model on the full BGG ratings matrix and blend CF-based scores with the existing content-based Jaccard scores, dramatically improving recommendation diversity and surfacing games that content similarity alone cannot discover.

### Design Notes
- **Content-Based Ceiling:** The current scoring pipeline uses Jaccard similarity on mechanics, categories, designers, and publishers — all content features. This works well for finding mechanically similar games, but it cannot discover "users who liked X also liked Y" patterns where X and Y share no visible content features. CF captures these latent preference dimensions.
- **Existing `ml_engine/` Foundation:** The repository already contains experimental LightFM scripts. This milestone productionizes that work into a recurring training pipeline with proper model serving.
- **Hybrid Blend:** The composite score becomes `α * content_score + (1-α) * cf_score`, where α is a configurable weight (default 0.6 content, 0.4 CF). For cold-start users with <5 rated games, α defaults to 1.0 (pure content) since CF has insufficient signal.

### Architecture Decisions
- **Training Pipeline:** Weekly SageMaker Processing Job (or a high-memory Lambda) that reads the full user ratings data from S3, trains a LightFM or Implicit ALS model, serializes the model artifact to S3 (`data/models/cf_model.pkl`), and generates a precomputed score matrix for the top 5000 games.
- **Serving:** The recommender Lambda loads the precomputed CF score lookup from S3 (a JSON/Parquet file mapping `{user_id: {game_id: cf_score}}`). For known users, blend CF scores with content scores. For unknown users, skip CF.
- **EventBridge Trigger:** Add a weekly EventBridge rule to trigger the training job, similar to the existing compactor schedule.

### Tasks
- [ ] **Training Script:** Productionize the LightFM training script from `ml_engine/` into a clean, tested module. Accept S3 paths for input ratings data and output model artifact. Include hyperparameter tuning for embedding dimensions and regularization.
- [ ] **Score Matrix Generation:** After training, generate a precomputed CF score lookup (top 500 candidate scores per user) and save to S3 as a compressed Parquet file.
- [ ] **SageMaker / Lambda Training Job:** Configure either a SageMaker Processing Job or a high-memory (10GB, 15-min timeout) Lambda to run the training script weekly.
- [ ] **EventBridge Schedule:** Add a weekly EventBridge trigger in the Terraform `eventbridge` module to invoke the training job.
- [ ] **Recommender Integration:** Update `scoring.py` to load CF scores from S3, blend with content scores using configurable weight α, and fall back to pure content scoring when CF scores are unavailable for a user.
- [ ] **Frontend Weight Slider:** Add a "Collaborative vs. Content" slider to the custom weights panel, controlling the α blend factor.
- [ ] **Unit Tests:** Test hybrid blending, cold-start fallback, model loading failure graceful degradation, and score normalization.

---

## Milestone 42: WebSocket Recommendation Streaming

### Objective
Replace the polling-based recommendation flow with API Gateway WebSocket connections that stream scored recommendation cards individually as they are generated, transforming perceived latency from "wait 10-30s for everything" to "first card in <2s."

### Design Notes
- **Current UX Problem:** Users submit a recommendation request and wait 10-30 seconds seeing only a spinner. The backend spends ~2-3s on scoring and ~8-15s on Bedrock narration. Users have no feedback during this time, leading to uncertainty, repeated submissions, and perceived slowness.
- **Streaming Model:** Since the LLM is responsible for selecting the final 10 games from the top 40 candidates and deduplicating game variants/editions, we cannot stream candidates to the client before the LLM makes its selections. Instead, we use Bedrock's Converse Stream API (`converse_stream`). The Lambda function parses the LLM's JSON output stream on the fly. As soon as a complete game object (containing the selected game name and narrated reason) is parsed, the Lambda resolves it to its catalog metadata and streams the final recommended card immediately to the client. This guarantees the user only sees the final 10 selected recommendations, appearing one-by-one as they are generated by the LLM.
- **Fallback:** If WebSocket connection fails (corporate firewalls, older browsers), fall back to the existing polling-based HTTP flow automatically.

### Architecture Decisions
- **API Gateway WebSocket API:** Create a separate WebSocket API in API Gateway (`wss://` endpoint) with `$connect`, `$disconnect`, and `$default` routes. The `$connect` route validates optional JWT auth. The `$default` route accepts recommendation request payloads.
- **Connection Management:** Store active WebSocket connection IDs in a lightweight DynamoDB table (`bgg-ws-connections`) with a 1-hour TTL. The recommendation Lambda posts messages to connection IDs via the API Gateway Management API.
- **Message Protocol:** Define a simple JSON message protocol: `{type: "recommendation", index: N, data: {...}}` for individual recommended cards, and `{type: "complete"}` for end-of-stream.

### Tasks
- [ ] **WebSocket API Gateway:** Create a new WebSocket API (`bgg-ws-api`) in the Terraform API Gateway module with `$connect`, `$disconnect`, and `$default` routes.
- [ ] **Connection DynamoDB Table:** Add a `bgg-ws-connections` table with `connectionId` partition key and TTL attribute.
- [ ] **WebSocket Lambda Handler:** Implement connection management (`$connect` stores connectionId, `$disconnect` removes it) and request routing (`$default` triggers recommendation flow with streaming output).
- [ ] **Streaming Recommendation Pipeline:** Modify `_handle_recommendations` to accept an optional WebSocket connection ID. When present, invoke the Bedrock Converse Stream API, parse the JSON stream chunk-by-chunk on the fly, resolve each selected game to its metadata, and stream the final 10 recommendations individually via WebSockets to the client as they are generated.
- [ ] **Frontend WebSocket Client:** Update `recommender/index.html` (or the extracted `recommender.js`) to establish a WebSocket connection, render cards as they stream in, and fall back to HTTP polling if WebSocket connection fails.
- [ ] **Unit Tests:** Test connection lifecycle, message serialization, and HTTP fallback behavior.

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
* **Milestone 36: Security Hardening & CORS Fixes** (Removed wildcard Lambda CORS headers, added API Gateway POST preflights, added regex username validation, moved Cognito Client/Pool IDs to GitHub secrets)
* **Milestone 37: DynamoDB Preferences Safety & Backend DRY Refactor** (Migrated preferences handler POST to table.update_item, centralized weight parsing helper in cache_utils.py, simplified client mock patching with dynamic __getattr__ module routing)
* **Milestone 38: Repository Hygiene & Code Quality** (Removed deprecated bgg_raw_to_compressed/ and ml_engine/ directories, extracted recommender index.html styles/scripts to external files, removed inert moved blocks from main.tf, and hardened test conftest AWS mock keys)
* **Milestone 39: Test Coverage Expansion** (S3 caching layer unit tests, Bedrock narration pipeline unit tests, Vitest + JSDOM frontend tests, CI path trigger fix)
* **Milestone 45: Recommendation Diversity Guard** (Deterministic post-scoring diversification pass to prevent mechanic and category clustering in Bedrock shortlists)
* **Milestone 40: Groups Page Redesign — Tabs & Per-Member Affinity** (Structured tabs layout, per-member taste alignment bar charts, dynamic color-coding, 100% max clamping, and backend Lambda scoring helper extraction)
* **Milestone 47: Release Polish (SEO, Favicon & Social Sharing)** (Registered jekyll-seo-tag and jekyll-sitemap, linked generated favicon and apple touch icons, audited page metadata, configured default OpenGraph/Twitter sharing cards, and added a custom glassmorphic 404 landing page)
* **Milestone 48: Collection Browser Image Fitting** (Updated collection browser game images to `object-fit: contain` with customized dark/light mode gradient containers to ensure aspect-ratio-aware fitting without cropping)


