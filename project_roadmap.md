# Boardgame Recommender - Project Roadmap

This document outlines the next steps and active architecture enhancements for the Boardgame Recommender project.

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

## Milestone 60: Playgroup Organizer Clean Modern Redesign

### Objective
Redesign the Playgroup Organizer planner view (`site_ui/groups/index.html`) with a clean, uncluttered modern layout featuring interactive attendee avatar chips, an integrated attendance counter, streamlined group header controls, and balanced two-column filter inputs.

### Design Notes
- **Interactive Member Avatar Chips:** Replace the oversized rectangular checkbox boxes with sleek, tactile avatar chips (`[● B player1 ✓]`, `[● J player2 ✓]`, `[● T player3 ✓]`). Toggling attendance updates the chip styling with emerald accents and active checkmarks.
- **Integrated Attendance Header:** Eliminate the empty standalone "Attendance Count" bar by embedding the live player counter directly into the section subheader (`Who is playing tonight? (3 attending)`), with clean `Select All` / `Clear` text action buttons.
- **Streamlined Group Header:** Display the active playgroup name with a compact total member badge and clean Edit/Delete action links.
- **Balanced Filter Controls:** Organize Pacing and Complexity dropdowns into a clean two-column grid with standardized glassmorphic input styling and a prominent, elegant `🎲 Generate Recommendations` action button.

### Architecture Decisions
- **Frontend Design System Updates:** Enhance `.member-chip`, `.groups-header-actions`, and `.planner-section` styling in `site_ui/assets/css/design-system.css` and `site_ui/groups/index.html`.
- **Vanilla JS Toggle Handlers:** Update `selectGroup`, `toggleMemberChecked`, `selectAll`, and `selectNone` in `groups/index.html` to manipulate chip classes and update the inline counter.

### Tasks
- [ ] **Attendee Avatar Chip Component:** Design and style `.member-chip` with circular initials avatar, member username, checkmark indicator, and active/inactive state transitions.
- [ ] **Inline Attendance Counter & Actions:** Redesign the attendance section header to include the inline attending badge and reposition Select All / Clear action links.
- [ ] **Group Header Alignment:** Refactor the active group header to display group title, member count pill, and Edit/Delete action buttons in a clean row.
- [ ] **Filter Controls & CTA Restyling:** Align Pacing and Complexity selects in a balanced grid and restyle the primary recommendation generator button.
- [ ] **Responsive & Theme Verification:** Verify layout across dark and light modes, and ensure smooth wrapping on mobile viewports (320px–768px).

---

## Milestone 61: Content-Based Scoring Normalization & Popularity De-biasing

### Objective
Fix candidate scoring homogenization across users by replacing unnormalized squared-tag accumulation with true cosine similarity, rebalancing default popularity weights, implementing continuous complexity distance matching, and upgrading the diversification pass to evaluate secondary mechanics.

### Design Notes
- **Candidate Vector Normalization:** Currently, `scoring.py` accumulates squared weights of matched mechanics without dividing by the candidate game's mechanic count $\sqrt{|\text{cand\_mechs}|}$. This causes multi-tag "kitchen-sink" Euros to systematically outscore tightly-designed niche games (e.g. roll-and-writes or trick-taking games) by nearly 2x for every user. True cosine similarity ($\frac{U \cdot G}{\|U\| \|G\|}$) eliminates this bias.
- **Popularity De-biasing:** Global rating popularity (`w_pop = 0.5`) adds a static baseline of ~0.85–0.90 to all top-50 BGG games, flattening user-specific taste differences. Lowering `w_pop` to 0.15–0.20 and raising `w_mech` to 0.60 restores taste alignment as the primary ranking driver.
- **Continuous Complexity Scoring:** The current four coarse complexity buckets produce almost identical normalized scores (~0.22 to 0.28) across both users. Replacing bucket ratios with a continuous Gaussian decay centered on the user's weighted average complexity creates genuine pacing differentiation.
- **Multi-Tag Diversification:** `diversify_candidates()` currently checks only `cand_mechs[0]`. Tagging with decayed weights across secondary mechanics prevents games sharing the same underlying sub-mechanisms from dominating the top 25 list.

### Architecture Decisions
- **True Cosine Normalization in `scoring.py`:** Update `calculate_game_score()` to compute $\frac{\sum W_{\text{user}}(m)}{\sqrt{|\text{cand\_mechs}|} \sqrt{\sum W_{\text{user}}^2}}$ for mechanics and categories.
- **Default Weight Adjustment in `cache_utils.py`:** Update `parse_weights()` defaults to `w_pop=0.20`, `w_mech=0.60`, `w_des=0.35`, `w_comp=0.35`, `w_cat=0.40`.
- **Gaussian Complexity Distance:** Compute user mean complexity $\mu_{\text{comp}}$ in the profile and calculate $\exp(-0.5 \times ((comp - \mu) / \sigma)^2)$ with $\sigma=0.75$.
- **Weighted Multi-Tag Diversity Tracker:** Update `diversify_candidates()` to accumulate fractional weights (1.0 for primary, 0.5 for secondary mechanics) with a composite cap.

### Tasks
- [ ] **True Cosine Similarity in `scoring.py`:** Refactor mechanic and category similarity calculations in `calculate_game_score()` to divide dot products by the candidate game's tag vector norm $\sqrt{|\text{cand\_tags}|}$.
- [ ] **Weight Defaults Rebalancing:** Update `parse_weights()` in `cache_utils.py` to reduce default `w_pop` to 0.20 and adjust `w_mech`, `w_des`, and `w_cat` weights.
- [ ] **Continuous Complexity Scoring:** Replace coarse bucket ratio in `calculate_game_score()` with Gaussian distance decay against user average complexity.
- [ ] **Multi-Tag Diversity Filtering:** Upgrade `diversify_candidates()` in `scoring.py` to evaluate all candidate mechanics and categories using decayed frequency counters.
- [ ] **Unit Tests:** Update and add unit tests in `test_bgg_recommender.py` to verify candidate norm scaling, balanced popularity influence, and diverse recommendation selection.

---

## Milestone 62: Taste Profile TF-IDF & Catalog Base-Rate Discounting

### Objective
Eliminate ubiquitous baseline noise from user taste profiles by applying Inverse Document Frequency (IDF) discounting based on BGG catalog mechanic and category frequencies, elevating users' distinctive preferences over ubiquitous tags.

### Design Notes
- **The Ubiquity Problem:** Ubiquitous mechanics ("Hand Management", "Solo / Solitaire Game", "Variable Player Powers") appear in 30–40% of all hobby board games. Because `calculate_damped_affinity()` applies logarithmic amplification $(1 + \alpha \ln(n))$, ubiquitous mechanics receive high multipliers while unique, distinctive mechanics (e.g., "Paper-and-Pencil", "Sealed Bid Auction", "Trick-taking") receive low multipliers. This causes raw taste profiles between different users to have ~90% cosine similarity.
- **TF-IDF Representation:** By calculating catalog-wide document frequencies $P(m) = N_m / N_{\text{catalog}}$ and applying an IDF factor $\text{IDF}(m) = \ln(1 + N_{\text{catalog}} / N_m)$, common mechanics are appropriately dampened while distinctive tastes are amplified.
- **Offline & Inline Parity:** Ensure identical TF-IDF logic is shared between the background analytics pipeline (`bgg_taste_analytics.py`) and the on-the-fly computation fallback (`compute_taste_profile_inline()` in `scoring.py`).

### Architecture Decisions
- **Catalog Frequencies Precomputation:** Precompute mechanic and category document frequencies from `catalog.parquet` and persist as an S3 asset (`data/catalog_feature_frequencies.json`) or bundle directly within the recommender layer.
- **IDF Profile Generation:** In `bgg_taste_analytics.py` and `scoring.py`, multiply raw damped affinities by the feature's IDF weight before finalizing user taste profile vectors.
- **Backward Compatibility:** Store both raw and IDF-weighted profiles or include IDF multipliers directly in taste profile JSON output so downstream consumers remain compatible.

### Tasks
- [ ] **Catalog Feature Frequencies Generator:** Create an automated task or helper to calculate category and mechanic frequencies across the BGG catalog parquet and save `catalog_feature_frequencies.json`.
- [ ] **TF-IDF Damping in `bgg_taste_analytics.py`:** Update `process_taste_profile()` to load feature frequencies and apply IDF weighting to mechanic and category affinities.
- [ ] **Inline Taste Profile Parity in `scoring.py`:** Update `compute_taste_profile_inline()` to apply the same catalog frequency discounting.
- [ ] **Taste Profile Schema Update:** Update taste profile JSON structure and document new metadata fields (`user_mean_complexity`, `idf_applied: true`).
- [ ] **Unit Tests:** Add unit tests in `test_bgg_taste_analytics.py` and `test_bgg_recommender.py` validating that distinctive mechanics rank above ubiquitous mechanics for specialized collections and verifying profile parity.

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


* **Milestone 41: Shareable Top 10 Recommendation Graphic & Image Export** (Implemented HTML5 Canvas generator module graphic_export.js for generating 1200x675 high-res social graphics of top 10 recommended games without AI text, added Export Image modal with live preview, 1-click Download PNG, Clipboard copy, and mobile Web Share API integration)
* **Milestone 58: Collection Browser Loading State & Skeleton Redesign** (Maintained visible persistent filter sidebar in loading state to eliminate layout jumping, rendered 8-card shimmering card grid skeleton matching default Card View)
* **Milestone 59: User Profile Skeleton Animation & Viewport Alignment Fix** (Fixed @keyframes shimmer in design-system.css and profile/index.html to animate background-position instead of transform: translateX, eliminating offscreen lateral drift during profile dashboard load)
* **Milestone 50: Local Development Environment** (Gitignored _config.local.yml and .env.local overrides, gen_local_config.py generator script, comprehensive LOCAL_DEVELOPMENT.md guide, and enhanced offline mock API handlers for /profile, /groups, and /preferences)
* **Milestone 57: Async Game Night Voting & Veto Session** (Defined bgg-game-night-sessions DynamoDB table with GSI and TTL, built sessions.py consensus engine with +2/+1/-99 veto scoring and tie-breaking, created standalone vote/index.html voting page with live countdown timer, and added host poll modal & Past Polls history tab on groups/index.html)



