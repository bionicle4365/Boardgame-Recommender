# Boardgame Recommender - Project Roadmap

This document outlines the next steps and active architecture enhancements for the Boardgame Recommender project.

---

---

## Milestone 44: Recommender Latency Optimization

### Objective
Reduce the recommendation refresh latency from 20+ seconds to under 8 seconds. This will be achieved by parallelizing S3 I/O operations and optimizing the Bedrock prompt and output token budgets without changing the LLM's selection capability or reducing recommendation diversity.

### Design Notes
- **Concise AI Explanations:** Enforce a strict length limit (e.g., maximum 12 words) on recommendation reasons in the Bedrock system prompt. Generating fewer output tokens dramatically reduces LLM latency since generation is the primary bottleneck.
- **25 Candidate Pool:** Retain the candidate shortlist at 25 games to preserve recommendation diversity and refresh variety, as input token count has negligible impact on prefill phase latency.
- **Parallel S3 Reads:** Use Python `concurrent.futures.ThreadPoolExecutor` to fetch user profiles, taste profiles, and hotness data from S3 concurrently rather than sequentially.

### Architecture Decisions
- **Token Constraints:** Set Bedrock `inferenceConfig` `maxTokens` limit lower (e.g., 800 tokens instead of 2048) to cap the execution time and enforce concise output.
- **Threading Model:** Use standard Python multiprocessing/threading libraries to run S3 operations concurrently within the Lambda execution environment.

### Tasks
- [ ] **Parallel S3 Fetching:** Refactor S3 calls in `bgg_recommender.py` and `scoring.py` to use a `ThreadPoolExecutor` for parallel downloads of user parquets, taste profiles, and hotness cache files.
- [ ] **Prompt Tuning (Concise Narration):** Update `narrate_recommendations` in `narration.py` to prompt Bedrock for short, punchy reasons (max 12 words) and adjust the `maxTokens` inference config down to 800.
- [ ] **Scoring Performance Tweaks:** Remove the redundant `catalog_df.copy()` operations from the recommendation routing path.
- [ ] **Verification:** Validate via logs that refresh requests return in < 8 seconds. Confirm that recommendations remain high-quality and reasons are concise.

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

## Milestone 49: Mobile UI Polish Pass

### Objective
Conduct a comprehensive mobile responsiveness audit and polish across every page (Home, Recommender, Collection Browser, Profile, Groups, Settings, 404) to ensure consistent, usable touch experiences on phones and small tablets — building on the responsive foundations from Milestone 10.

### Design Notes
- **Scope:** This is a general polish pass, not a single-page fix. Every page needs a mobile audit for layout overflow, tap target sizing, text readability, and scroll behavior.
- **Breakpoints:** Audit all pages at 320px, 375px, 414px, and 768px widths. Ensure no horizontal scrolling, no clipped content, and no overlapping elements at any width.
- **Touch Targets:** All interactive elements (buttons, links, radio cards, tabs) must meet a minimum 44×44px touch target per WCAG 2.1 guidelines.
- **Focus Areas:** Recommender wizard modal (personality cards and taste test carousel), Groups tabs and per-member affinity bars, Profile dashboard charts, Collection grid/table toggle, and Settings form layout.

### Architecture Decisions
- **CSS-Only Where Possible:** Prefer CSS media query fixes and flexbox/grid adjustments over JS-based responsive logic. All changes should go in existing page-level CSS or `design-system.css`.
- **No Layout Rewrites:** Preserve the existing desktop layouts. Only add/adjust `@media` rules for widths ≤768px and ≤480px.

### Tasks
- [ ] **Recommender Page Mobile Audit:** Fix wizard modal sizing, personality option cards overflow, taste test carousel image scaling, form field widths, and slider touch areas on narrow viewports.
- [ ] **Collection Browser Mobile Audit:** Verify collection grid cards, filter panel, taste profile charts, and table rows at 320-414px widths. Fix any horizontal overflow or text clipping.
- [ ] **Profile Dashboard Mobile Audit:** Ensure profile header, overview stats, Chart.js visualizations, and rating distribution bars scale correctly and remain readable on mobile.
- [ ] **Groups Page Mobile Audit:** Verify tab navigation, attendee list, per-member affinity bars, playgroup analytics charts, and planner empty states at mobile widths.
- [ ] **Settings Page Mobile Audit:** Check form layout, weight sliders, and preference dropdowns for usability on narrow screens.
- [ ] **Home Page & 404 Mobile Audit:** Verify landing page hero, feature cards, and 404 page layout at mobile widths.
- [ ] **Global Navigation Mobile Audit:** Re-verify the mobile drawer from Milestone 10 still works correctly with all current pages and account dropdown interactions.
- [ ] **Verification:** Manual test all pages at 320px, 375px, 414px, and 768px. Confirm no horizontal scrolling, no overlapping elements, and all interactive elements have adequate touch targets.

---

## Milestone 50: Local Development Environment

### Objective
Enable full local Jekyll development with real API endpoints and Cognito credentials by providing a secure, gitignored configuration override system — supporting both `.env.local` file and Jekyll config override approaches.

### Design Notes
- **Problem:** The `_config.yml` uses `PLACEHOLDER_API_URL`, `PLACEHOLDER_COGNITO_CLIENT_ID`, and `PLACEHOLDER_COGNITO_USER_POOL_ID` which are only substituted via GitHub Actions secrets during CI deployment. When running `bundle exec jekyll serve` locally, these remain as literal placeholder strings, causing API calls and authentication to fail silently.
- **No Secrets in Repo:** The real values must never be committed. Both approaches must use gitignored files.
- **Two Approaches:** Document and support: (a) a `_config.local.yml` override file used with Jekyll's multi-config flag, and (b) a `.env.local` file with a helper script that generates the local config override automatically.

### Architecture Decisions
- **Approach A — Jekyll Config Override:** Create a `_config.local.yml` template (gitignored) that users copy and fill in with real values. Run Jekyll with `bundle exec jekyll serve --config _config.yml,_config.local.yml` — the second config file overrides matching keys in the first.
- **Approach B — `.env.local` + Script:** Create a `.env.local.example` file documenting required variables. Create a `scripts/gen_local_config.py` (or `.sh`) script that reads `.env.local` and generates `_config.local.yml` from it. Add `.env.local` and `_config.local.yml` to `.gitignore`.
- **Documentation:** Add a `LOCAL_DEVELOPMENT.md` guide documenting both approaches, prerequisites (Ruby, Bundler, Jekyll), and troubleshooting steps.

### Tasks
- [ ] **Gitignore Updates:** Add `_config.local.yml`, `.env.local`, and any generated local config files to the repository `.gitignore`.
- [ ] **Config Override Template:** Create `site_ui/_config.local.yml.example` with commented placeholder entries for `api_url`, `cognito_client_id`, `cognito_region`, and `cognito_user_pool_id`.
- [ ] **Env File Template:** Create `site_ui/.env.local.example` listing all required environment variables with descriptions.
- [ ] **Config Generator Script:** Create `scripts/gen_local_config.py` that reads `site_ui/.env.local` and writes `site_ui/_config.local.yml` with the real values.
- [ ] **Local Development Guide:** Create `LOCAL_DEVELOPMENT.md` documenting both approaches, prerequisites, and step-by-step setup instructions.
- [ ] **Mock API Enhancement:** Review and update the existing `fetchApi` mock fallback in `utils.js` to cover more endpoints accurately for fully offline development when even the real API URL is unavailable.
- [ ] **Verification:** Confirm both approaches produce a working local site with functional API calls and Cognito authentication when real credentials are provided.

---

## Milestone 52: New User AI Narration Context

### Objective
Detect inline/new-user recommendation requests (Quick Taste Test and Personality Test) and use a tailored Bedrock narration prompt that generates meaningful, contextual explanations without referencing a user's BGG collection — which doesn't exist for these users.

### Design Notes
- **Problem:** The current Bedrock narration prompt instructs the LLM to "relate the recommended game to 1 or 2 specific board games they already like or own from their list." For Quick Taste Test users, this list is just the 5-11 seed games they thumbs-upped (e.g., Catan, Wingspan). For Personality Test users, this list is *completely empty* ("No games rated/owned yet"). The resulting AI narration sounds nonsensical — referencing games the user never mentioned, or producing generic filler text.
- **Fix Strategy:** Detect `is_inline` mode in the narration pipeline and switch to an alternative prompt that:
  - For **taste test users** (who have a sparse `liked_games_str` from seed games): References their seed game preferences but acknowledges the profile is approximate. Focuses on mechanic/thematic alignment rather than deep collection knowledge.
  - For **personality test users** (who have only `inline_weights` and no liked games): Focuses entirely on the user's declared playstyle preferences (cooperative vs competitive, complexity level, play time, theme, luck preference, etc.) rather than referencing any games.
- **Personality Context Forwarding:** The compiled personality answers (q1-q7 values) should be forwarded through `query_params` or the `inline_weights` object so the narration prompt can reference the user's specific quiz answers (e.g., "Since you prefer cooperative games with moderate complexity...").

### Architecture Decisions
- **Narration Module Change:** Add an `is_inline` flag and `inline_weights` context to `narrate_recommendations()` in `narration.py`. When `is_inline` is true, use an alternative prompt template that omits the "relate to games they already like" instruction.
- **Personality Context:** Include the personality quiz answer labels (not just the derived weights) in the `inline_weights` payload so the prompt can reference natural-language preferences like "cooperative", "heavy brain-burner", "sci-fi & fantasy", etc.
- **No Scoring Changes:** The scoring pipeline remains unchanged — only the narration prompt text differs for inline users.

### Tasks
- [ ] **Pass Inline Context to Narration:** Update `_handle_recommendations` in `bgg_recommender.py` to pass `is_inline` and `inline_weights` to the `narrate_recommendations` function.
- [ ] **Alternative Narration Prompt:** Create a new prompt template in `narration.py` for inline users. For taste test users, reference seed games lightly. For personality test users, reference playstyle preferences (format, complexity, theme, interaction style) directly.
- [ ] **Forward Personality Labels:** Update the frontend `compilePersonalityWeights()` in `recommender.js` to include a `personality_answers` object (e.g., `{format: "cooperative", complexity: "heavy", theme: "scifi", ...}`) alongside the derived mechanic/category/complexity weights.
- [ ] **Backend Parsing:** Ensure `bgg_recommender.py` extracts the `personality_answers` from the `inline_weights` payload and passes it through to the narration module.
- [ ] **Unit Tests:** Test the alternative prompt generation for both taste-test and personality-test user types. Verify the prompt does not contain "relate to games they already like" for inline users. Verify personality labels are correctly injected.
- [ ] **Verification:** Run both new user paths end-to-end and confirm the AI narration references appropriate context (seed game preferences for taste test, playstyle descriptors for personality test).

---

## Milestone 53: Recommendation Card Redesign

### Objective
Redesign the recommendation results cards to be more compact and space-efficient on wide monitors, reducing excessive vertical scrolling while preserving the glassmorphism design system and all existing card information.

### Design Notes
- **Problem:** The current recommendation cards use a single-column full-width layout (`grid-template-columns: 1fr`). On wide monitors (≥1024px), each card stretches across the full content area, making the AI narration text lines very long and requiring excessive vertical scrolling to see all 10 recommendations.
- **Design Exploration:** Before implementing, create visual mockups of multiple layout options for user review:
  - **Option A:** 2-column grid on desktop (≥1024px) — cards sit side-by-side, roughly halving vertical space.
  - **Option B:** Compact horizontal card layout — reduced padding, smaller thumbnail, condensed stats row, single-column but less vertical height per card.
  - **Option C:** Hybrid — 2-column grid with compact cards for maximum density.
- **Constraints:** Must preserve: game thumbnail, title link, Match # badge, all stat badges (rating, complexity, players, playtime, year), AI narration text, and group member affinities when present. Must maintain glassmorphism visual style and dark/light mode support.

### Architecture Decisions
- **Mockup First:** Generate visual mockups before writing code. The user wants to see options and choose a direction.
- **CSS-First Changes:** The card layout changes should be primarily CSS (grid and flex adjustments in `design-system.css`), with minimal or no JS changes to the `renderRecommendationCard` function in `utils.js`.
- **Responsive Breakpoints:** The redesign targets desktop (≥1024px). Tablet (768-1023px) and mobile (<768px) should remain single-column.

### Tasks
- [ ] **Generate Mockups:** Create visual mockups for 2-3 layout options (2-column grid, compact single-column, hybrid) for user review and selection.
- [ ] **User Review:** Present mockups and collect design direction feedback before implementation.
- [ ] **Implement Chosen Layout:** Update `design-system.css` with the selected layout's grid/flex rules, padding, and sizing adjustments at the ≥1024px breakpoint.
- [ ] **Update Card Rendering (if needed):** Adjust `renderRecommendationCard` in `utils.js` if the chosen layout requires HTML structure changes.
- [ ] **Dark/Light Mode Verification:** Confirm the redesigned cards look correct in both light and dark mode themes.
- [ ] **Responsive Verification:** Verify the new layout gracefully collapses to single-column at tablet and mobile widths.

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
* **Milestone 34: Empty States, Onboarding Guidance & Cold-Start Rating Flow** (Polished empty state preview overlay, Gamer Quick Taste Test with Round 2 adaptive selection, Casual Personality Test with 7 playstyle questions, S3-bypass inline profile/weights POST submissions, and mechanic-based dislike exclusions)
* **Milestone 54: Scoring Pipeline Corrections** (Projected true cosine similarity, dislike threshold boundary lowered to 6.5, group re-computation deduplication, BGG_TESTING env var test bypass, and sum-based complexity weighting)
* **Milestone 51: Taste Test Image Loading Fix** (Replaced broken full-sized BGG CDN images with verified smaller thumbnail URLs in the seed catalog array, and added a fallback placeholder handler to the HTML markup)
