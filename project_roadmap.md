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
 
 ## Milestone 11: Playgroup Taste Profile & Visualizations
 
 ### Objective
 Construct visual taste profile and library statistics charts displaying a playgroup's collective preferences, play time ranges, and complexity distributions.
 
 ### Tasks
 - [ ] Import `Chart.js` via CDN on the playgroup dashboard page.
 - [ ] Aggregate playgroup metrics dynamically across the collections of all attending members:
   - Categories and mechanics count frequencies.
   - Game complexity values (low/medium/high distribution).
   - Play time durations (short/medium/long distribution).
 - [ ] Render interactive and responsive taste profile visualizations:
   - A radar chart displaying top game mechanic affinities.
   - A horizontal bar chart displaying top game category affinities.
   - A doughnut or pie chart displaying the game complexity profile distribution.
   - A vertical bar chart displaying game duration ranges.
 - [ ] Build visual summaries (glassmorphism cards) for group statistics: Total unique games, average group complexity, and average BGG rating.
 
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
 
 ## Milestone 18: Varied & Engaging AI Recommendation Explanations
 
 ### Objective
 Refine the recommendation engine to produce more varied, descriptive, and accurate AI explanations that avoid repetitive sentence structures.
 
 ### Tasks
 - [ ] **System Prompt Refactoring:** Refactor the LLM system prompt context in `bgg_recommender.py` to command varied, natural, and expressive justifications.
 - [ ] **Exclusion of Templated Forms:** Instruct the LLM to avoid static templated prefixes (e.g., "If you enjoyed X, you will love Y" or "Since you enjoyed X, you'll enjoy Y").
 - [ ] **Multidimensional Justifications:** Require justifications to highlight specific reasons such as thematic overlap, mechanical synergy, player count adaptability, or pacing/complexity compatibility.
 - [ ] **Variance Assertions:** Update unit tests to enforce style variance checks on mock Bedrock output processing.
 
 ---
 
 ## Milestone 18: BGG GeekPreview Convention Recommendations
 
 ### Objective
 Synchronize the recommender database with BoardGameGeek GeekPreviews, allowing users to filter recommendations to only games debuting at upcoming conventions (e.g. Gen Con, SPIEL Essen).
 
 ### Tasks
 - [ ] **Nightly Scraper:** Implement a nightly scheduled Lambda function that uses a `curl` subprocess to discover and fetch active/upcoming convention lists from BGG's `/api/geekpreviewitems` endpoint.
 - [ ] **S3 Database Cache:** Persist active preview game ID arrays to `active_previews.json` in S3.
 - [ ] **Lambda Filter Pipeline:** Update `bgg_recommender.py` to parse `preview_id` query parameters, filter candidates to the allowed preview ID list, and ignore games missing from the offline Parquet catalog.
 - [ ] **Dropdown Selector:** Build a dynamic frontend select box in the Recommender UI that displays only active conventions (hiding the selector entirely when no conventions are active).
 - [ ] **Unit Tests:** Author tests to verify preview filtering constraints and graceful fallback behaviors.
 
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
