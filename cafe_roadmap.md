# Board Game Cafe & Bar Edition - Project Roadmap

This document outlines the milestones and engineering architecture for adapting the **Boardgame Recommender** platform into a turnkey digital sommelier and table recommendation solution for board game cafes, bars, and lounges.

Detailed architecture diagrams, data models, and API specifications are documented in [docs/cafe_edition_design.md](file:///d:/Git/Boardgame-Recommender/docs/cafe_edition_design.md).

---

## Milestone C1: Self-Service Cafe Onboarding & Dynamic Venue Registry

### Objective
Create a frictionless, self-service onboarding flow that allows cafe owners and managers to register their venue in under 3 minutes, automatically validate their BGG collection, configure table counts and Wi-Fi credentials, and immediately download printable table tent QR codes.

### Design Notes
- **Zero-Touch Self-Service:** Cafe operators must not need developer intervention or manual config file edits to get their venue live.
- **Real-Time BGG Validation:** Before completing registration, the onboarding wizard validates the cafe's BGG username against the BGG API proxy, previews their total owned game count, and detects how many games have shelf location tags in their comments.
- **Custom URL Slug:** Each cafe chooses a vanity slug (e.g. `the-malt-and-meeple`), checked for uniqueness.
- **Immediate Value on Completion:** The moment registration finishes, the cafe owner gets a 1-click download of ready-to-print table tent graphics and their live table URL.

### Architecture Decisions
- **DynamoDB Venue Registry:** Create a new DynamoDB table `bgg-cafes` with `cafe_id` partition key and a GSI on `owner_cognito_id`.
- **S3 Cache Mirror:** On venue creation/update, mirror metadata to `s3://boardgame-app/data/cafes/{cafe_id}/meta.json` and update `data/cafes_registry.json` for fast in-memory reading by recommender Lambdas.
- **API Endpoints:**
  - `GET /cafe/validate-bgg?username=XXX`: Anonymous pre-flight check that queries BGG API proxy and parses owned game count and sample shelf comments.
  - `POST /cafe/onboard`: Cognito-authenticated registration endpoint that stores venue metadata in `bgg-cafes` DynamoDB and dispatches an initial scrape job to `USER_SQS_QUEUE_URL`.
  - `GET /cafe/meta?cafe_id=XXX`: Public endpoint returning cafe branding, Wi-Fi info, and table count.
- **Onboarding UI:** Dedicated web flow at `site_ui/cafe/onboard.html` styled with the existing glassmorphic design system.

### Tasks
- [x] **DynamoDB Terraform Module:** Define `bgg-cafes` DynamoDB table with `cafe_id` PK and `owner_cognito_id` GSI in `infrastructure/dynamodb/`.
- [x] **BGG Validation Endpoint:** Implement `_handle_validate_bgg()` in backend Lambda to query BGG XML API2, verify ownership count, and test regex extraction on comments.
- [x] **Onboarding API Handler:** Implement `_handle_cafe_onboard()` in backend Lambda to persist venue to DynamoDB, mirror to S3, and enqueue initial scrape to SQS.
- [x] **API Gateway Route:** Add `/cafe/validate-bgg` (public) and `/cafe/onboard` (Cognito authorizer) routes in API Gateway Terraform.
- [x] **Frontend Onboarding Wizard:** Build `site_ui/cafe/onboard.html` with real-time BGG collection verification, live shelf note preview, table count selector, and Wi-Fi configuration.
- [x] **Automated QR Generator Hook:** Trigger automated table tent bundle generation upon successful onboarding.
- [x] **Unit & Integration Tests:** Test BGG username validation, slug uniqueness checks, DynamoDB persistence, and SQS queue dispatch.

---

## Milestone C2: Cafe Inventory Ingestion, On-Demand Sync & Manual Catalog Management

### Objective
Build the data ingestion and catalog management system that syncs a cafe's collection from BGG, enables cafe staff to trigger immediate on-demand re-syncs, allows direct manual game additions and shelf location edits, and durably merges manual overrides with automated syncs.

### Design Notes
- **On-Demand "Sync from BGG":** When a cafe finishes logging new games on BGG, staff can click "🔄 Sync Library from BGG" in their portal, immediately pulling updates into their cafe collection without waiting for weekly batch jobs.
- **Manual Game Additions (No BGG Required):** Staff can search the catalog and add newly acquired games directly into the cafe's library with shelf coordinates, custom notes, and drink pairings — ideal for putting new games on the shelf immediately.
- **Manual Shelf Location Editing:** Staff can adjust shelf coordinates (e.g. moving a game from `Shelf A-1` to `Shelf C-4`) directly from the management interface.
- **Durable Overrides Preservation:** Manual additions and shelf edits are stored in `data/cafes/{cafe_id}/overrides.json`. Automated BGG syncs preserve manual overrides so staff modifications are never overwritten.
- **Ownership Filter:** Only games marked as `own=1` in the cafe's BGG collection (plus manual additions) are ingested into the venue's active inventory.

### Architecture Decisions
- **Storage Location:** Save cafe libraries to `s3://boardgame-app/data/cafes/{cafe_id}/collection.parquet` and manual customizations to `s3://boardgame-app/data/cafes/{cafe_id}/overrides.json`.
- **Lambda Extension:** Extend [`bgg_user_data_scraper`](file:///d:/Git/Boardgame-Recommender/bgg_user_data_scraper) to support cafe mode (`is_cafe=true`), extracting collection data and parsing shelf tags into explicit DataFrame columns: `['id', 'name', 'shelf_location', 'custom_notes', 'in_stock', 'year_published']`.
- **Merge Engine:** Implement `merge_cafe_inventory(bgg_df, overrides_json)` that merges BGG items with manual additions, applies shelf coordinate overrides, and removes manually deleted games.
- **API Endpoints:**
  - `POST /cafe/sync` (authenticated): Dispatches an immediate scrape job and clears the venue's recommendation cache.
  - `GET /cafe/search-games?query=...` (authenticated): Queries the catalog database for autocomplete title searches.
  - `POST /cafe/inventory/manual` (authenticated): Adds a manual game or updates shelf coordinates in `overrides.json`.
- **EventBridge Schedule:** Weekly trigger invoking cafe sync across all active venues in `bgg-cafes`.

### Tasks
- [ ] **Collection Scraper Extension:** Update `bgg_user_data_scraper` to parse shelf locations from `comment` and `private_comment` fields using venue-specific regex patterns from `bgg-cafes`.
- [ ] **Parquet Generator & Merger Engine:** Output normalized `collection.parquet` merging BGG scraped items with `overrides.json` (preserving manual additions, shelf overrides, and exclusions).
- [ ] **On-Demand Sync Endpoint:** Add `POST /cafe/sync` (authenticated) to trigger immediate re-scrape for a venue and invalidate recommendation cache.
- [ ] **Manual Game Search & Add API:** Implement `GET /cafe/search-games?query=...` and `POST /cafe/inventory/manual` to search the master catalog and append manual additions/shelf edits to `overrides.json`.
- [ ] **EventBridge Weekly Trigger:** Configure automated weekly EventBridge rule to iterate registered cafes and trigger background sync.
- [ ] **Unit Tests:** Add tests for shelf location regex extraction, on-demand sync triggering, manual override merging, and preserving manual additions across syncs.

---

## Milestone C3: Cafe-Scoped Candidate Pool & 30-Second Table Vibe Engine

### Objective
Extend the recommendation engine in [`bgg_recommender.py`](file:///d:/Git/Boardgame-Recommender/bgg_recommender/bgg_recommender.py) to accept a `cafe_id`, strictly restrict candidates to that cafe's in-stock collection, and provide an instant "Table Vibe Check" scoring algorithm for patrons without BGG accounts.

### Design Notes
- **Hard Candidate Boundary:** When `cafe_id` is supplied, candidate games *must* strictly be a subset of the cafe's active inventory. A game cannot be recommended if the cafe does not own it.
- **Frictionless Non-BGG Patrons:** 80%+ of cafe patrons do not have BGG accounts. The recommender must instantly compute high-quality recommendations based on 3 inputs: player count, time window, and mood vibe.
- **Ownership Inversion:** Unlike the standard recommender (which excludes games the user already owns), cafe mode recommends games *from* the cafe's collection, even if a visiting hobbyist already owns it at home.
- **Sommelier Persona in Bedrock:** Customize the Nova Micro narration prompt so Bedrock acts as the cafe's lead game guru, emphasizing teach ease, group dynamics, and why it fits a table with drinks.

### Architecture Decisions
- **New Query Parameters:** Add `cafe_id`, `vibe` (`party`, `casual_strategy`, `deep_strategy`, `cooperative`, `direct_conflict`), and `table` to `GET /recommendations` in [`bgg_recommender.py`](file:///d:/Git/Boardgame-Recommender/bgg_recommender/bgg_recommender.py).
- **Vibe Weight Matrix:** Map vibe presets directly to target complexity Gaussian curves ($\mu, \sigma$) and normalized mechanic/category weight vectors in [`scoring.py`](file:///d:/Git/Boardgame-Recommender/bgg_recommender/scoring.py) without requiring offline taste profile generation.
- **Bedrock Narration:** Update [`narration.py`](file:///d:/Git/Boardgame-Recommender/bgg_recommender/narration.py) with a dedicated cafe prompt template that includes shelf location and estimated rules teach time.
- **S3 Response Caching:** Cache cafe recommendations with a composite key: `data/recommendation_cache/cafe_{cafe_id}_{vibe}_{player_count}_{duration_pref}.json` with a 7-day TTL.

### Tasks
- [ ] **Cafe Inventory Loader:** Add `get_cafe_inventory(cafe_id)` in [`cache_utils.py`](file:///d:/Git/Boardgame-Recommender/bgg_recommender/cache_utils.py) with in-memory caching and S3 fallback.
- [ ] **Candidate Masking:** Integrate cafe inventory filtering into `_handle_recommendations` in [`bgg_recommender.py`](file:///d:/Git/Boardgame-Recommender/bgg_recommender/bgg_recommender.py).
- [ ] **Vibe Profile Generator:** Implement `get_vibe_weights(vibe_key)` in [`scoring.py`](file:///d:/Git/Boardgame-Recommender/bgg_recommender/scoring.py) generating continuous complexity penalties and affinity vectors.
- [ ] **Bedrock Sommelier Prompt:** Implement `build_cafe_sommelier_prompt()` in [`narration.py`](file:///d:/Git/Boardgame-Recommender/bgg_recommender/narration.py).
- [ ] **API Gateway Route Updates:** Ensure `/recommendations` accepts and validates `cafe_id` parameter.
- [ ] **Unit Tests:** Test candidate pool restriction (asserting zero non-cafe games are returned), vibe profile weighting, and cache hit/miss behavior.

---

## Milestone C4: Mobile-First Cafe Patron Portal & Vibe Check UI

### Objective
Design and implement a mobile-first, glassmorphic patron web interface at `site_ui/cafe/` that provides a seamless 3-tap recommendation experience when scanning a table QR code.

### Design Notes
- **Immediate Value:** Patrons should see recommendations within 10 seconds of scanning the table QR code.
- **Design Aesthetic:** Co-branded header with cafe logo and table badge, sleek dark glassmorphism styling consistent with `site_ui/assets/css/design-system.css`, high-contrast text readable in dim bar lighting.
- **The 3-Tap Vibe Quiz:**
  1. *Player Count:* Tactile pill selectors `[ 2 ] [ 3 ] [ 4 ] [ 5 ] [ 6+ ]`.
  2. *Time Window:* `[ < 30m ] [ 45-60m ] [ 90m+ ]`.
  3. *Vibe:* Visual cards with icons (`🍻 Party`, `🏰 Casual Strategy`, `🧠 Heavy Strategy`, `🤝 Cooperative`).
- **Hobbyist Bypass:** Clean accordion toggle: *"Have BGG accounts? Enter usernames for group recommendations."*
- **Game Cards:** Highlight physical shelf location (e.g. `📍 Shelf B-3`), complexity level, estimated teach time, and a 1-tap "Watch Video Rules" button.

### Architecture Decisions
- **Jekyll Page:** Create `site_ui/cafe/index.html` with dedicated styles in `site_ui/assets/css/cafe.css` and logic in `site_ui/assets/js/cafe.js`.
- **Dynamic Cafe Loading:** Read `:cafe_id` from URL path/query parameter (`?cafe=...&table=...`) and fetch cafe branding from `data/cafes_registry.json` or backend endpoint `GET /cafe/meta?cafe_id=...`.
- **Client State:** Store table number and current filter selections in `sessionStorage` for smooth navigation between screens.

### Tasks
- [ ] **Cafe Portal Layout:** Build `site_ui/cafe/index.html` using existing glassmorphic design tokens and responsive CSS grid.
- [ ] **Interactive Vibe Quiz Component:** Build tactile single-select chips with smooth CSS transitions for player count, time, and vibe.
- [ ] **Recommendation Results View:** Design mobile-first game cards featuring shelf location pill, teach time badge, and Bedrock sommelier quote.
- [ ] **Hobbyist BGG Input:** Add collapsible input field allowing 1–5 BGG usernames with group scoring integration.
- [ ] **Error & Empty States:** Friendly empty states if no cafe games match strict filters with one-tap filter relaxation buttons.
- [ ] **Visual Testing:** Verify responsive rendering across mobile screen sizes (iPhone Safari, Android Chrome).

---

## Milestone C5: "Watch It Played" Rules Video & Media Integration

### Objective
Integrate concise video rules tutorials directly into recommendation cards so patrons can immediately learn how to play without waiting for busy floor staff or reading paper rulebooks.

### Design Notes
- **Patron Behavior:** In a loud cafe or bar, reading a 12-page rulebook stalls the table. A 3-minute video overview (*Watch It Played*, *3-Minute Board Games*, or BGG video links) gets the game started immediately.
- **Modal In-App Player:** Video must play inside a responsive in-app modal to prevent patrons from being redirected away to YouTube and abandoning the portal.
- **Data Source:** BGG XML API2 `/thing?videos=1` provides curated instructional video IDs for almost every catalog game.

### Architecture Decisions
- **Video Metadata Ingestion:** Extract primary instructional video URL/ID during game scraper cataloging or cache a lightweight lookup table in S3: `data/game_videos.json`.
- **Frontend Video Modal:** Accessible, responsive iframe modal component in `site_ui/cafe/` with clean close gestures and playback controls.

### Tasks
- [ ] **BGG Video Link Extractor:** Add video link extraction logic to [`bgg_game_data_scraper`](file:///d:/Git/Boardgame-Recommender/bgg_game_data_scraper) prioritizing instructional/how-to-play tags.
- [ ] **Video URL Resolution in Recommender:** Include `rules_video_url` in the `/recommendations` API response payload.
- [ ] **Frontend Video Modal:** Build accessible glassmorphic video modal in `site_ui/cafe/index.html` with YouTube embed and fallback search link.
- [ ] **Teach Time Badge:** Display rulebook complexity and estimated rules teach time directly adjacent to the video button.
- [ ] **Unit & E2E Tests:** Test video URL resolution and modal open/close behaviors.

---

## Milestone C6: Table QR Code Generator & Real-Time Table Voting

### Objective
Provide cafe managers with a print-ready table tent QR generator and connect the existing game night voting system ([`sessions.py`](file:///d:/Git/Boardgame-Recommender/bgg_recommender/sessions.py)) so patrons sitting at the same table can vote on the top candidate games from their phones.

### Design Notes
- **Physical QR Table Tents:** Beautiful, printable PDF/SVG templates with cafe branding, table number badge, Wi-Fi details, and QR code leading directly to that table's URL.
- **Table Voting Integration:** When recommendations are generated, any patron at the table can tap *"Vote with Table"*. This automatically creates an ephemeral voting session prepopulated with the top 4 recommended games.
- **Fast Consensus:** Friends scan the vote QR or open the shared link, cast $+2 / +1 / \text{veto}$ votes, and see the winning game in under 60 seconds.

### Architecture Decisions
- **Reusing Voting Infrastructure:** Hook directly into existing [`sessions.py`](file:///d:/Git/Boardgame-Recommender/bgg_recommender/sessions.py) and `bgg-game-night-sessions` DynamoDB table.
- **Session Auto-Creation:** Add a single-tap endpoint `POST /cafe/vote/start` that instantiates a session with `group_name = "{Cafe Name} - Table {Table Number}"`.
- **QR Generation Tool:** Create a Python/HTML5 generator script in `scripts/generate_cafe_table_qrs.py` that outputs high-resolution print-ready vector SVGs and PDFs.

### Tasks
- [ ] **QR Generator Script:** Implement `scripts/generate_cafe_table_qrs.py` accepting cafe ID, table count range (e.g. Tables 1–30), logo, and Wi-Fi credentials.
- [ ] **Printable Table Tent Template:** Design clean, modern printable SVG template (double-sided folding table tent).
- [ ] **One-Tap Table Session Creation:** Add "Start Table Vote" action on `site_ui/cafe/index.html` initializing session via existing API.
- [ ] **Cafe Voting View:** Create a streamlined, mobile-optimized voting card view matching the cafe branding.
- [ ] **Integration Tests:** Test end-to-end flow from table QR generation to multi-user voting consensus.

---

## Milestone C7: Cafe Floor Staff Portal & Inventory Availability Toggle

### Objective
Create a lightweight, mobile-optimized staff portal for cafe floor staff and game masters to mark games as "In Use at Table X", "Damaged", or "Back on Shelf", instantly updating recommendation candidate pools.

### Design Notes
- **Problem Solved:** Nothing frustrates a patron more than being recommended a game only to discover another table is currently playing it.
- **Staff UX:** Servers have 5 seconds between orders. The interface must feature instant barcode/search lookup and 1-tap availability toggles.
- **Security:** Protected via Cognito authentication or a simple cafe PIN code to prevent unauthorized patron modification.

### Architecture Decisions
- **Inventory State Storage:** Store live availability status in DynamoDB or an S3 overlay: `data/cafes/{cafe_id}/live_status.json`.
- **Cache Invalidation:** When a game is marked "In Use", invalidate active recommendation cache keys for that cafe or filter out in-memory.
- **API Endpoint:** Add `POST /cafe/inventory/status` allowing authenticated staff to toggle `in_stock: true | false`.

### Tasks
- [ ] **Status API Handler:** Implement `_handle_cafe_inventory_status()` in backend Lambda to update game availability.
- [ ] **Staff Dashboard UI:** Build `site_ui/cafe/staff.html` with instant fuzzy search, availability toggles, table assignment, a prominent "🔄 Sync from BGG" button, and an "➕ Add Game to Shelf" catalog search modal.
- [ ] **Inline Shelf Editor:** Enable quick editing of shelf locations directly on existing games from the staff dashboard with instant persistence to `overrides.json`.
- [ ] **Live Inventory Filter:** Ensure `_handle_recommendations` excludes games with `in_stock == false`.
- [ ] **Auth Protection:** Protect staff routes using Cognito authentication with cafe staff role or venue PIN.
- [ ] **Unit Tests:** Test status updates, authorization validation, shelf coordinate editing, and candidate pool updates.

---

## Milestone C8: Cafe Library Analytics & Table Insights Dashboard

### Objective
Provide cafe owners with an automated analytics dashboard detailing patron search trends, most requested mechanics, busiest table party sizes, and shelf utilization.

### Design Notes
- **Actionable Business Intelligence:**
  - *"Which games on our shelves are never recommended or played?"* (Candidates for selling).
  - *"What are patrons searching for that we don't own?"* (Acquisition recommendations).
  - *"What is the peak party size on Friday night vs. Sunday afternoon?"*
- **Privacy First:** Strictly anonymous, aggregated session logs. No patron personal data is tracked or stored.

### Architecture Decisions
- **Telemetry Logging:** Log lightweight anonymous JSON events to CloudWatch / S3 Athena on recommendation and vote events: `{cafe_id, table_id, timestamp, player_count, vibe, selected_game_id}`.
- **Analytics Reporting:** Athena query or weekly Python aggregator script outputting `data/cafes/{cafe_id}/analytics_summary.json`.
- **Owner Dashboard:** Analytics view in `site_ui/cafe/dashboard.html` with charts for popular vibes, player counts, and shelf heatmaps.

### Tasks
- [ ] **Telemetry Logger:** Add anonymous structured logging to recommendation and voting Lambda handlers.
- [ ] **Athena / S3 Log Partitioning:** Configure S3 partition scheme for cafe analytics events.
- [ ] **Analytics Aggregator Script:** Create `scripts/aggregate_cafe_analytics.py` computing weekly utilization metrics.
- [ ] **Owner Analytics UI:** Build glassmorphic dashboard with chart visualizations (Chart.js or Vanilla SVG) in `site_ui/cafe/dashboard.html`.
- [ ] **Documentation:** Document metrics definitions and data retention policies.
