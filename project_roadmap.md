# Boardgame Recommender - Project Roadmap

This document outlines the next steps and active architecture enhancements for the Boardgame Recommender project.

---

## Milestone 28: Shared CSS Design System & JS Utilities Extraction

### Objective
Eliminate duplicated CSS variables, component styles, and JavaScript logic across all site pages by extracting shared code into centralised design-system and utility files, reducing maintenance burden and ensuring visual consistency.

### Design Notes
- **CSS Duplication:** Every page (`recommender`, `collection`, `groups`, `profile`, `settings`) re-declares `:root` CSS variables and duplicates common styles (header sections, card patterns, form inputs, spinner/loading animations, glassmorphism tokens). Extracting these into a single `assets/css/design-system.css` file and linking it from `default.html` will cut ~30-40% of duplicated CSS.
- **JS Duplication:** API call logic, `localStorage` helpers (username get/set), auth state checks, and card-rendering functions are copy-pasted across page `<script>` blocks. A shared `assets/js/utils.js` module will consolidate these into reusable functions.

### Architecture Decisions
- **CSS Strategy:** Create `assets/css/design-system.css` containing all shared `:root` variables, glassmorphism tokens, typography, base card/form/spinner component styles, and responsive breakpoints. Include it via `<link>` in `_layouts/default.html`. Each page retains only its unique styles.
- **JS Strategy:** Create `assets/js/utils.js` exporting common helpers: `fetchApi(endpoint, params)` with error handling, `getStoredUsername()` / `setStoredUsername()`, and shared card-rendering functions. Include it via `<script>` in `_layouts/default.html`.

### Tasks
- [x] **Audit Shared Styles:** Catalogue all duplicated CSS across page files and identify the shared superset of variables, tokens, and component classes.
- [x] **Create `design-system.css`:** Extract shared `:root` variables, glassmorphism tokens, typography, header-section, form-card, spinner, card, and button component styles into `site_ui/assets/css/design-system.css`.
- [x] **Link Design System in Layout:** Add `<link>` to `design-system.css` in `_layouts/default.html` and remove duplicated declarations from each page file.
- [x] **Create `utils.js`:** Extract shared JavaScript helpers (API fetch wrapper, localStorage username helpers, auth state checks) into `site_ui/assets/js/utils.js`.
- [x] **Link Utils in Layout:** Add `<script>` to `utils.js` in `_layouts/default.html` and refactor each page to use the shared helpers instead of inline duplicates.
- [x] **Visual Regression Check:** Verify all pages render identically after extraction using local Jekyll server.

---

## Milestone 29: Dark Mode Toggle

### Objective
Add a user-togglable dark mode to the site, leveraging the existing CSS custom property design system for minimal implementation effort with high visual impact.

### Design Notes
- **Variable-Driven Approach:** The site already uses CSS custom properties (`--background`, `--card-bg`, `--text-main`, `--text-muted`, `--border`, `--sidebar-bg`, etc.) defined in `:root`. Dark mode requires only a second set of variable overrides applied when a `data-theme="dark"` attribute is set on `<html>`.
- **Persistence:** The user's theme preference is saved to `localStorage` and applied on page load before first paint to avoid a flash of the wrong theme.
- **Toggle Placement:** A sun/moon icon toggle button in `header.html`, next to the existing auth badge.

### Architecture Decisions
- **CSS Scope:** Dark mode variables are defined under `html[data-theme="dark"]` in the shared design system CSS file (depends on Milestone 28, or can be added to `default.html` `<style>` block if done independently).
- **Sidebar:** The sidebar already uses a dark palette (`--sidebar-bg: #0f172a`), so it requires minimal or no changes.

### Tasks
- [x] **Define Dark Palette:** Create a `html[data-theme="dark"]` rule overriding all `:root` colour variables (`--background`, `--card-bg`, `--text-main`, `--text-muted`, `--border`, `--header-bg`, `--glass-bg`, shadows, etc.) with appropriate dark equivalents.
- [x] **Toggle Button UI:** Add a sun/moon toggle button in `_includes/header.html` with smooth icon transition animation.
- [x] **Toggle Logic:** Implement JS in `header.html` to toggle `data-theme` on `<html>`, persist to `localStorage`, and restore on page load (before DOM renders to prevent flash).
- [x] **Page-Specific Overrides:** Audit page-level colour overrides (e.g. collection green accents, profile purple accents) and ensure they work against the dark background.
- [x] **Visual Verification:** Test all pages (home, collection, recommender, groups, profile, settings) in both light and dark mode on desktop and mobile.

---

## Milestone 30: Skeleton Loading States

### Objective
Replace spinner-based loading indicators with animated skeleton placeholder UI that mirrors the final content layout, improving perceived performance and creating a more premium feel.

### Design Notes
- **Current State:** The collection browser, recommender, and groups pages use green spinner cards during loading. Skeleton loaders (pulsing grey placeholder rows/cards matching the final layout shape) provide better spatial context and feel significantly faster.
- **Implementation:** Pure CSS approach using `@keyframes` pulse animation on placeholder `<div>` elements styled to match card/row dimensions. No JS library needed.

### Tasks
- [x] **Skeleton CSS Component:** Create reusable `.skeleton-card`, `.skeleton-row`, and `.skeleton-text` CSS classes with a subtle pulse animation (`background: linear-gradient` shimmer effect).
- [x] **Recommender Skeleton:** Replace the recommender loading spinner with 4-6 skeleton recommendation cards matching the final card layout (image placeholder, title bar, description lines).
- [x] **Collection Skeleton:** Replace the collection loading spinner with skeleton table rows matching the column layout.
- [x] **Groups Skeleton:** Replace the playgroup loading states with skeleton cards matching the group panel layout.
- [x] **Visual Verification:** Confirm skeleton layouts align with final rendered content on desktop and mobile viewports.

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

## Milestone 32: API Gateway Response Compression

### Objective
Enable gzip response compression on API Gateway to reduce payload transfer sizes by 60-70%, improving mobile load times for recommendation and collection API responses.

### Design Notes
- **Current State:** The recommender Lambda returns raw uncompressed JSON. Recommendation payloads with 10+ rich game objects (including thumbnails, mechanics lists, AI narration text) can be 15-30KB. Gzip compression typically reduces this to 5-10KB.
- **API Gateway Support:** API Gateway v2 (HTTP API) supports response compression natively via the `minimum_compression_size_in_bytes` setting.

### Architecture Decisions
- **Terraform Configuration:** Set `minimum_compression_size_in_bytes` on the API Gateway stage in the existing Terraform infrastructure module. A threshold of 1024 bytes (1KB) ensures only meaningful payloads are compressed.

### Tasks
- [ ] **Terraform Update:** Add `minimum_compression_size_in_bytes = 1024` to the API Gateway stage configuration in `infrastructure/apigateway/`.
- [ ] **CORS Header Verification:** Ensure `Content-Encoding` is included in exposed CORS headers if needed.
- [ ] **Client Verification:** Verify that the Jekyll frontend `fetch()` calls correctly decompress gzip responses (browsers handle this automatically via `Accept-Encoding` headers).

---

## Milestone 33: Lightweight Recommendation Feedback Loop

### Objective
Allow authenticated users to provide lightweight thumbs-up / thumbs-down feedback on individual recommendation results, stored in DynamoDB for future use as a pre-filter exclusion list — without adding computational overhead to the scoring pipeline.

### Design Notes
- **Performance Concern:** The recommendation pipeline is already latency-sensitive. Feedback must not add computation to the scoring loop. Instead, feedback is applied as a simple **pre-filter**: thumbs-down game IDs are excluded from candidates before scoring begins, and thumbs-up game IDs are never excluded even if other filters would remove them.
- **Storage:** Feedback is stored in the existing DynamoDB preferences table (already used by `bgg_preferences` Lambda) as a `recommendation_feedback` attribute: `{ "liked": ["id1", "id2"], "disliked": ["id3"] }`.
- **Scope:** This milestone covers the DynamoDB storage, the pre-filter integration, and the frontend UI buttons. It explicitly does **not** modify mechanic weight calculations or the Bedrock prompt.

### Architecture Decisions
- **DynamoDB Schema:** Add a `recommendation_feedback` map attribute to the existing user preferences item. No new table needed.
- **Pre-Filter Only:** In `_handle_recommendations`, after loading user profiles and before candidate scoring, load the user's disliked game IDs from DynamoDB and remove them from the candidates DataFrame. This is a single set-difference operation with negligible cost.

### Tasks
- [ ] **DynamoDB Schema Update:** Add `recommendation_feedback` attribute (map of `liked` and `disliked` string sets) to the user preferences item schema in `bgg_preferences`.
- [ ] **Preferences API Endpoints:** Add `PUT /preferences/feedback` and `GET /preferences/feedback` routes to the preferences Lambda for storing and retrieving feedback.
- [ ] **Recommender Pre-Filter:** In `_handle_recommendations`, load disliked game IDs from DynamoDB (if user is authenticated) and exclude them from candidates before scoring.
- [ ] **Frontend Feedback Buttons:** Add 👍 / 👎 buttons to recommendation cards (visible only when logged in). On click, call the preferences API to persist feedback and visually update the card state.
- [ ] **Unit Tests:** Test the pre-filter exclusion logic and the feedback persistence endpoints.

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
