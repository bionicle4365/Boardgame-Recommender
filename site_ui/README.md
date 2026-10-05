# Site UI - Frontend Web Application

The frontend web application for the Boardgame Recommender platform, built with **Jekyll**, modern **Vanilla CSS**, and lightweight **Vanilla JavaScript**. It delivers a mobile-first, responsive glassmorphic user experience without the overhead of heavy frontend frameworks.

---

## Directory Structure

```text
site_ui/
├── _config.yml               # Production Jekyll configuration
├── _data/                    # Static datasets & menu structures
├── _includes/                # Modular HTML partials
│   ├── auth_modal.html       # Amazon Cognito login/signup modal
│   ├── footer.html           # Footer partial with status & links
│   └── header.html           # Navigation bar with user avatar & menu
├── _layouts/
│   └── default.html          # Base HTML5 layout and head metadata
├── assets/
│   ├── css/
│   │   └── design-system.css # Glassmorphic design tokens, utilities & themes
│   ├── js/
│   │   ├── utils.js          # Cognito auth client, API fetchers, Toast alerts
│   │   ├── recommender.js    # Recommendation state machine & card rendering
│   │   └── graphic_export.js # HTML5 Canvas 1200x675 social graphic exporter
│   └── img/                  # Logos, icons, and og-image banners
├── collection/               # BGG collection explorer & filtering grid
├── groups/                   # Playgroup organizer & voting host dashboard
├── profile/                  # Multi-dimensional taste profile & radar charts
├── recommender/              # Core AI recommendation interface & filter sidebar
├── settings/                 # Custom algorithm weight sliders & account settings
├── vote/                     # Standalone table voting & veto portal
└── tests/                    # Vitest unit test suite for frontend modules
```

---

## Key Pages & Features

### 1. Recommender (`/recommender`)
- **Interactive Filter Sidebar:** Filter by player count, publishing year range, duration, complexity, convention preview, and custom weight profiles.
- **Two-Phase Rendering:** Returns instant candidates with generic reasons before Bedrock Nova Micro delivers personalized AI narrations.
- **Graphic Social Export (`graphic_export.js`):** Generates a high-resolution 1200x675 PNG summary graphic of the top 10 recommended games ready for Discord or Instagram sharing.
- **Cold-Start Wizard:** Guides users without a BGG collection through a 3-step triage to construct an inline taste vector.

### 2. Collection Browser (`/collection`)
- Fast client-side collection search and filtering for any BGG user handle.
- Renders dual Card and Table views with shimmer skeleton loading states.

### 3. Playgroup Organizer (`/groups`)
- Save recurring gaming groups (e.g. "Friday Night Crew").
- Interactive attendee avatar chips with a live attendance counter.
- One-tap consensus poll launcher that initializes a voting session in DynamoDB.

### 4. Live Table Voting (`/vote?id=XXXXXX`)
- Ephemeral, shareable voting portal.
- Friends cast $+2$ (Favorite), $+1$ (Interested), or $-99$ (Veto) votes to resolve game night selection disputes in under 60 seconds.

### 5. Taste Profile Dashboard (`/profile`)
- Displays TF-IDF mechanic and category affinity distributions.
- Shows user's rating-weighted mean complexity and distinctive niche tags.

---

## Authentication & Security

- **Cognito Integration (`utils.js`):** Client-side authentication using the Amazon Cognito Identity SDK.
- Handles user registration, email verification, login, JWT token refresh, and self-service password recovery.
- Passes `Authorization: Bearer <JWT>` to protected endpoints (`/preferences`).

---

## Local Development & Testing

### Running Jekyll Locally
```bash
cd site_ui
bundle install
bundle exec jekyll serve --livereload
```
Visit `http://localhost:4000`.

### Running Frontend Unit Tests (Vitest)
```bash
cd site_ui
npm install
npm test
```
