# Boardgame Recommender - Project Roadmap

This document outlines the next steps and active architecture enhancements for the Boardgame Recommender project.

---

## Milestone 9: Advanced Filter Builder (Hard Exclusions & Designer Weights)
 
 ### Objective
 Add advanced UI filters to exclude specific categories, mechanics, or designers, and perform dynamic filtering in Python before calling Bedrock.
 
 ### Tasks
 - [ ] Implement exclusion UI multi-select lists for mechanics, categories, and designers.
 - [ ] Update frontend script to deliver exclusion collections as URL query parameters.
 - [ ] Update serving Lambda backend to dynamically parse exclusions and filter candidates in Python prior to Bedrock invocation.
 
 ---
 
 ## Milestone 11: Taste Analytics Backend

 ### Objective
 Build the event-driven backend pipeline that automatically derives and persists a user's taste profile — weighted mechanic/category affinities, complexity preference, and designer/publisher affinity scores — whenever their BGG collection is scraped. Expose the profile via a dedicated API endpoint so downstream UI milestones and the recommendation engine can consume it without recomputing from raw data.

 **Architecture:** `S3 PutObject (data/users/*.parquet)` → S3 Event Notification → SQS (`taste_analytics_queue`) → `bgg_taste_analytics` Lambda → S3 (`data/users/{username}_taste_profile.json`)

 The taste profile JSON schema captures:
 - `mech_weights` — mechanic name → rating-weighted affinity score
 - `cat_weights` — category name → rating-weighted affinity score
 - `complexity_weights` — dictionary of rating-weighted complexity bucket affinities (Light, Medium-Light, Medium-Heavy, Heavy)
 - `designer_weights` — designer → affinity score
 - `publisher_weights` — publisher → affinity score
 - `generated_at` — ISO timestamp for staleness checks

 ### Tasks

 #### Taste Analytics Lambda
 - [x] **New Lambda — `bgg_taste_analytics`:** Implement a new Lambda that reads a username from an SQS message, downloads the user's collection parquet and `catalog.parquet` from S3, computes weighted mechanic/category affinities, average complexity, and designer/publisher affinity scores, and saves the result as `data/users/{username}_taste_profile.json` in S3.

 #### Event-Driven Pipeline Infrastructure
 - [x] **S3 Event Notification:** Configure an S3 event notification on the `boardgame-app` bucket to publish `ObjectCreated` events for the prefix `data/users/` and suffix `.parquet` to the `taste_analytics_queue` SQS queue.
 - [x] **SQS Queue & DLQ:** Create the `taste_analytics_queue` SQS queue with a dead-letter queue (`taste_analytics_dlq`) and a redrive policy (e.g. `maxReceiveCount = 3`).
 - [x] **CloudWatch Alarm:** Create a CloudWatch alarm on `taste_analytics_dlq` `ApproximateNumberOfMessagesVisible > 0` to alert when a taste profile fails to generate after all retries.
 - [x] **Terraform Module:** Add a new `taste_analytics` Terraform module containing the Lambda, SQS queue, DLQ, S3 event notification, IAM role, and CloudWatch alarm.

 #### API & Recommender Integration
 - [x] **Profile API Endpoint:** Add a `GET /profile?username=X` route to the API Gateway that returns the pre-built taste profile JSON directly from S3, for consumption by the analytics dashboard and playgroup page without triggering a full recommendation run.
 - [x] **Recommender Optimisation:** Update `bgg_recommender.py` to load `data/users/{username}_taste_profile.json` from S3 at the start of scoring and use its pre-computed weights directly — skipping the inline derivation step. Fall back to computing inline if the profile is absent or stale (older than the user's collection parquet).

 ---


 ## Milestone 16: Unified Analytics & Taste Profile UI

 ### Objective
 Deliver a cohesive analytics experience across two UI surfaces — the Collection Browser and the Playgroup dashboard — using a shared Chart.js design system. Both pages consume the `GET /profile?username=X` endpoint introduced in Milestone 11 to display rating-weighted taste profiles and collection statistics with a consistent visual language.

 ### Open Questions
 - **Dynamic Filtering Interaction:** Should the collection analytics charts automatically filter based on active search queries and faceted filters (e.g., clicking "2 Players" filters the table and updates all charts)? Or should they always represent the entire library?
 - **Handling N/A Ratings:** If a user has only rated a few games, the rating distribution chart will have mostly `N/A` values. Should the chart fall back to showing BGG community rating distribution, or only analyze games with valid user ratings?
 - **CSV/JSON Export:** Should the collection browser provide an option to download the parsed collection data as a clean CSV or JSON file for offline analysis?

 ### Tasks

 #### Shared Design System (implement first)
 - [ ] **Chart.js Design Tokens:** Define a shared colour palette, font styles, and chart defaults (border radius, gridline opacity, tooltip styles) to be reused across all chart instances on both pages.
 - [ ] **Reusable Card Component:** Implement a glassmorphism summary card pattern (HTML/CSS) that is used consistently on both the collection browser analytics tab and the playgroup dashboard.

 #### Collection Browser Analytics Tab
 - [ ] **Tabbed UI Design:** Refactor [index.html](file:///d:/Git/Boardgame-Recommender/site_ui/collection/index.html) to support tab buttons ("Grid View" and "Collection Analytics") with clear view panels.
 - [ ] **Summary Cards:** Render glassmorphism summary cards for key library stats: Total Games, Average Personal vs BGG Rating, Total Plays, #1 Played Game.
 - [ ] **Chart.js Integration:** Implement responsive chart containers for playtime distribution, player count distribution, rating distribution, and most-played leaderboards using the shared design system.
 - [ ] **Taste Profile Charts:** Fetch `GET /profile?username=X` and render a radar chart of top mechanic affinities and a horizontal bar chart of top category affinities for the individual user.
 - [ ] **Dynamic Data Wiring:** Wire Javascript triggers to extract stats from `gamesData` (and optionally react to active filters) to update all Chart.js instances.

 #### Playgroup Taste Profile Visualizations
 - [ ] **Profile Fetching & Merge:** For each playgroup member, fetch their pre-built taste profile from `GET /profile?username=X`. Merge individual profiles into a combined group affinity view (weighted average of mechanic/category scores). Fall back to client-side frequency counting if a profile is not yet available.
 - [ ] **Taste Profile Charts:** Render a radar chart (top mechanic affinities), horizontal bar chart (top category affinities), doughnut chart (complexity distribution), and vertical bar chart (duration ranges) using the shared design system.
 - [ ] **Group Summary Cards:** Render glassmorphism summary cards for group statistics: Total Unique Games, Average Group Complexity, Average BGG Rating.

 ---
 
 ## Milestone 17: Cold-Start Onboarding (BGG Profile Bypass & Rating Flow)

 ### Objective
 Provide a seamless recommendation flow for users without a BoardGameGeek profile. The user is walked through a two-round adaptive game rating flow (👍 / 👎 / Haven't played it) that collects enough signal to build a temporary taste profile, which is submitted inline to the existing recommendation API.

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
 
 ## Milestone 18: Varied & Engaging AI Recommendation Explanations

 ### Objective
 Eliminate the repetitive sentence structure across the 10 AI-generated recommendation explanations by fixing the specific prompt instructions that cause the model to pattern-match a single template phrase. Each recommendation must use a distinct framing angle while remaining a single punchy sentence.

 ### Root Cause
 The current prompt at the explanation instruction step includes a concrete example phrase: *"If you enjoyed Gloomhaven and Mage Knight, you will love this game's use of card-driven hand management."* LLMs pattern-match on examples in their instructions — this single example causes the model to use an identical "If you enjoyed X..." opener for all 10 recommendations. Two compounding factors: temperature is set to `0.3` (too deterministic for varied prose) and there is no system-role message to establish a more expressive writing persona.

 ### Tasks

 #### Prompt Changes (`bgg_recommender.py`)
 - [ ] **Remove the Example Phrase:** Delete the parenthetical example sentence from the explanation instruction. Examples act as templates the model replicates; removing it is the single highest-impact change.
 - [ ] **Enumerate Rotation Angles:** Replace the current explanation instruction with an explicit list of 7 framing angles the model must rotate through across the 10 recommendations, using each at least once. Each recommendation must use a different angle — do not repeat the same sentence opener or structure:
   1. *Mechanical alignment* — how its play mechanics match what they enjoy
   2. *Thematic/narrative resonance* — shared atmosphere, setting, or tone
   3. *Complexity fit* — how it matches or meaningfully challenges their weight preference
   4. *Player count and social dynamic* — how it suits their typical group size or dynamic
   5. *Novelty and contrast* — what's fresh or distinct from what they already own
   6. *Session pacing* — how the game's length and flow suit their preferences
   7. *Designer/publisher lineage* — shared creative DNA with games they rate highly
 - [ ] **Hard Ban on Repeated Openers:** Explicitly instruct the model that no two recommendations may begin with the same word or phrase, and that "If you enjoyed..." may be used at most once across all 10.
 - [ ] **Raise Temperature:** Increase `temperature` from `0.3` to `0.6` in the Bedrock `inferenceConfig`. Lower temperature is appropriate for JSON structure but suppresses prose variation. If JSON parsing failures increase, add a `system` role message (using Bedrock's `system` parameter in the Converse API) to reinforce structured output at the model level, allowing temperature to stay at `0.6`.

 #### Testing
 - [ ] **Opener Uniqueness Test:** Add a unit test that asserts no two `reason` strings in a mock Bedrock response share the same first 4 words.
 - [ ] **Angle Coverage Test:** Add a unit test that passes a mock response through a keyword classifier and asserts that at least 4 of the 7 angles are represented across the 10 reasons (mechanics, theme, complexity, player count, novelty, pacing, lineage).

 ---
 
 ## Milestone 19: BGG GeekPreview Convention Recommendations

 ### Objective
 Synchronize the recommender with BoardGameGeek GeekPreviews so users can filter recommendations to games debuting at upcoming conventions (e.g. Gen Con, SPIEL Essen). A weekly ECS Fargate task scrapes active convention IDs and fetches full game metadata via BGG's internal `geekpreviewitems` JSON API, persisting results to S3 for the recommender and frontend to consume.

 ### API Research Notes

 **`GET /api/geekpreviewitems?previewid={id}`** — confirmed publicly accessible with no authentication. Accepts plain Python `requests` calls. Returns a JSON array of all games in the given convention preview, including inline:
 - `objectid` — BGG game ID
 - `geekitem.item.links.boardgamemechanic` / `boardgamecategory` / `boardgamedesigner` / `boardgamepublisher` — full metadata
 - `yearpublished`, `minplayers`, `maxplayers`, `minplaytime`, `maxplaytime`, `minage`
 - `primaryname.name` — game name
 - `thumbnail` — cover art URLs
 - `availability_status` — `forsale`, `preorder`, etc.
 - `stats.musthave`, `stats.interested` — community interest signals
 - `showcount=N` is a valid parameter to limit page size

 Since the API returns full mechanics/category metadata inline, **no Selenium CSV download and no separate catalog enrichment is needed for game data**. The Selenium/browser requirement is reduced to a single lightweight render of the `/previews` index page, solely to discover active `previewid` integer values. The rest of the pipeline uses plain HTTP.

 **Convention ID Discovery:** `GET /api/geekpreviews` returns HTTP 400 — no listing endpoint exists. The `/previews` index page requires JavaScript rendering (returns 403 to plain HTTP). A lightweight Playwright render (ECS Fargate, already in infrastructure) of `/previews` extracts the convention list and their numeric IDs from the rendered DOM. This is the **only** browser-dependent step.

 ### Architecture

 ```
 EventBridge (weekly) → ECS Fargate task
     1. Playwright render of /previews → extract active convention names + previewid integers
     2. For each active convention:
        requests.get(/api/geekpreviewitems?previewid=X) → full game list with metadata
     3. Save data/active_previews.json to S3
        Format: [{convention_id, name, date, games: [{objectid, name, mechanics, categories, ...}]}]

 EventBridge (daily) → Lambda (bgg_preview_refresh)
     1. Read active_previews.json from S3
     2. If no active conventions → exit immediately (fast no-op)
     3. For each active convention, re-call /api/geekpreviewitems?previewid=X
     4. Merge new games into existing convention entry, overwrite S3
     (No browser needed — previewid integers are already known)

 GET /recommendations?convention_id=gencon2026
     → Recommender reads active_previews.json from S3 (cached in-memory, 1-hour TTL)
     → Builds temporary candidate dataframe from convention game list
     → Scores against user taste profile as normal
     → Bedrock selects top 10 with explanations
 ```

 ### Tasks

 #### Weekly Scraper (ECS Fargate) — Convention Discovery
 Convention lists change infrequently; a weekly run is sufficient for discovering new previews. This is the only step requiring a browser.
 - [ ] **Convention Discovery:** Use Playwright in the existing ECS Fargate task infrastructure to render `https://boardgamegeek.com/previews`, extract all upcoming convention names, dates, and `previewid` integers from the rendered DOM (filtering to conventions with future dates only).
 - [ ] **Initial Game Data Fetch:** For each newly discovered `previewid`, call `GET /api/geekpreviewitems?previewid={id}` with `requests`. Parse the JSON response to extract `objectid`, `primaryname.name`, mechanic names, category names, player counts, playtime, and thumbnail URL per game.
 - [ ] **S3 Persistence:** Save `data/active_previews.json` to S3 in the format `[{convention_id, name, date, games: [{objectid, name, mechanics, categories, min_players, max_players, playing_time, thumbnail}]}]`. Update the file atomically on each weekly run.
 - [ ] **EventBridge Schedule:** Add a weekly EventBridge rule (e.g. every Monday 06:00 UTC) to trigger the ECS Fargate scraper task.

 #### Daily Refresh Lambda — Active Convention Game Lists
 Publishers frequently add games to a convention preview once it goes live. The daily refresh re-fetches game lists for currently active conventions. No browser is required since `previewid` integers are already stored in `active_previews.json`.
 - [ ] **New Lambda — `bgg_preview_refresh`:** Implement a Lambda that reads `data/active_previews.json` from S3. If no conventions are currently active (all dates in the past), exit immediately. For each active convention, re-call `GET /api/geekpreviewitems?previewid={id}` and merge any newly added games into the convention's game list. Overwrite `active_previews.json` in S3 atomically.
 - [ ] **EventBridge Daily Schedule:** Add a daily EventBridge rule (e.g. 06:00 UTC) to trigger `bgg_preview_refresh`. The Lambda's fast-exit path means cost is negligible on days with no active conventions.

 #### Recommender Integration
 - [ ] **Convention Filter:** Update `bgg_recommender.py` to accept an optional `convention_id` query parameter. When present, load `data/active_previews.json` from S3 (cache in-memory alongside the catalog), build a temporary candidate dataframe from that convention's game list, and score it against the user's taste profile. Fall back to the full catalog if the convention is not found or the preview file is unavailable.
 - [ ] **In-Memory Cache:** Cache `active_previews.json` in a global Lambda variable (same pattern as `CATALOG_CACHE`) with a 1-hour TTL to avoid re-downloading on every warm invocation.

 #### Frontend
 - [ ] **Convention Dropdown:** On page load, fetch `active_previews.json` from S3 (or via a new `GET /active-previews` API Gateway route) to populate a dropdown of upcoming conventions. Hide the dropdown entirely when no conventions are active. Append `?convention_id=X` to the recommendations request when a convention is selected.
 - [ ] **Convention Badge:** When viewing recommendations filtered by a convention, display a badge or header indicating which convention is being shown (e.g. "Gen Con 2026 Previews").

 #### Testing
 - [ ] **Unit Tests:** Verify the convention filter correctly restricts the candidate pool to the preview game list, that games missing from the preview list are excluded, and that the fallback to the full catalog works when `active_previews.json` is absent or the convention ID is not found.

 ---
 
 ## Milestone 20: Cognito Verification Email Delivery Setup
 
 ### Objective
 Establish reliable verification email delivery for Cognito authentication using AWS Simple Email Service (SES) to ensure sign-up codes/links are successfully received by users.
 
 ### Tasks
 - [ ] Configure AWS SES (Simple Email Service) verified identity (domain or email).
 - [ ] Update Cognito User Pool configuration in Terraform to integrate SES for email delivery using the `email_configuration` block.
 - [ ] Grant Cognito User Pool execution role permission to send emails via SES.
 - [ ] Customize confirmation code verification email templates (HTML/Text).
 - [ ] Verify email delivery using verified sandbox emails or requests for SES production access.
 
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
 * **Milestone 12: Production Observability, Rate Limiting, & Cost Protection** (API limits, structured logging, alarms)
 * **Milestone 13: Serverless Cost Optimization & Glue Crawler Bypass** (Python pandas/pyarrow compaction Lambda, bypass Athena)
 * **Milestone 14: Recommender Personalization via Duration & Complexity Weighting** (Pacing/complexity soft-weighting, Bedrock justifications, frontend selectors)
 * **Milestone 15: User Authentication & Profile Persistence** (Amazon Cognito integration, DynamoDB preferences/playgroups synchronization, custom glassmorphism modal UI)
