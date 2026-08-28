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

## Milestone 57: Async Game Night Voting & Veto Session

### Objective
Enable playgroup hosts to generate a lightweight, shareable voting link from their group recommendations where attendees can vote (👍 Want to Play / 😐 Fine / ❌ Veto) on a candidate shortlist, automatically calculating the group consensus pick, locking results at a user-defined deadline, and preserving past poll history for the creator.

### Design Notes
- **Frictionless Participant Flow:** No registration or login required for participants. Group members simply open the link, enter their name (or select from the playgroup roster), and vote with 1-click reaction buttons on 3–6 candidate games.
- **Configurable Poll Duration & Deadline:** The creator selects how long the poll remains open (e.g., 2 hours, 6 hours, 24 hours, 3 days, or 7 days). A live countdown is shown on the voting page; once expired, voting automatically locks and the final consensus winner is declared.
- **Veto-Aware Consensus Algorithm:** Calculates the winning game by scoring:
  - 👍 `+2 points`
  - 😐 `+1 point`
  - ❌ `-99 points` (Hard Veto: immediately disqualifies the game if any attendee vetoes it).
  - Tie-breaker: Highest original playgroup recommendation score.
- **Creator History & Results Archive:** The original poll creator can view a "📜 Poll History" dashboard in their Playgroup Planner (`groups/index.html`) to review past sessions, see who voted what, and look back at past game night winners.

### Architecture Decisions
- **Storage:** DynamoDB `bgg-game-night-sessions` table with partition key `session_id` (8-char nanoid) and TTL expiration attribute `expires_at` (set to `closes_at + 60 days` so historical results persist well after the poll closes). Items store `creator_id` (Cognito Sub / BGG username), `group_name`, `created_at`, `closes_at`, `candidates` array, and a `votes` map `{ participant_name: { game_id: "yes"|"neutral"|"veto" } }`.
- **Global Secondary Index (GSI):** Add a `creator_id-created_at-index` GSI to DynamoDB to allow fast queries for all past sessions created by a user.
- **Lambda Routes:** Add route handlers in `bgg_recommender.py`:
  - `POST /session` (Authenticated): Creates a new voting session with candidates and custom `duration_hours`.
  - `GET /session/{session_id}` (Public): Retrieves the session candidates, deadline countdown, and current vote tallies.
  - `POST /session/{session_id}/vote` (Public): Submits or updates a participant's vote payload before `closes_at`.
  - `GET /sessions` (Authenticated): Retrieves all past and active sessions created by `creator_id` for the history dashboard.
- **Frontend Voting Interface:** Add a standalone, mobile-first page `site_ui/vote/index.html` with live countdown and voting controls.

### Tasks
- [ ] **DynamoDB Table & GSI:** Define `bgg-game-night-sessions` table in Terraform with `session_id` partition key, `creator_id-created_at-index` GSI, and TTL attribute `expires_at`.
- [ ] **Session Backend API:** Implement `create_session` (with `duration_hours`), `get_session` (with deadline enforcement), `submit_vote`, and `list_creator_sessions` route handlers in the recommender Lambda.
- [ ] **Consensus Scoring Function:** Implement consensus tallying math in `scoring.py` with hard veto disqualification, tie-breaking, and closed-poll status checks.
- [ ] **Playgroup Host Session Creator:** Add a "🗳️ Start Voting Session" modal on `groups/index.html` with candidate picker and duration selector (2h / 6h / 24h / 3d / 7d).
- [ ] **Playgroup History Dashboard:** Add a "📜 Past Polls" tab on `groups/index.html` listing past game night polls, attendance, and winners.
- [ ] **Participant Voting Page:** Build `site_ui/vote/index.html` with countdown timer, glassmorphic cards, candidate box art, 👍/😐/❌ vote buttons, and a live results banner showing the consensus pick.
- [ ] **Unit Tests & Verification:** Test duration calculation, deadline expiration locking, GSI history queries, vote serialization, and consensus calculation with vetoes.

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


