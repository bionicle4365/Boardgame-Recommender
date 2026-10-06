---
name: site-ui-expert
description: Expert in HTML, Vanilla CSS, Jekyll configurations, client-side Javascript, Vitest unit testing, and responsive glassmorphic design systems. Use this skill when modifying frontend layouts, stylesheets, templates, client scripts, or Vitest unit tests.
---

## Guidelines for Frontend Development

### UI & Styling Standards
- **Aesthetic Principles**: Create premium, modern layouts with curated palettes, subtle micro-animations, smooth transitions, and glassmorphic elements.
- **Vanilla CSS**: Prioritize Vanilla CSS for styling. Do not use TailwindCSS unless explicitly instructed.
- **Responsive Layout**: Ensure grids, containers, and cards scale properly across mobile, tablet, and desktop viewports. Prevent horizontal overflows.
- **Loading UX**: Implement animated skeleton loading templates during async fetch operations.

### Testing & Verification
- **Automated Unit Testing**: Run frontend unit tests using Vitest (`npm test` or `npm --prefix site_ui test`). All test suites in [site_ui/tests/](file:///d:/Git/Boardgame-Recommender/site_ui/tests/) must pass before deploying.
- **UI Verification Policy**: Automated browser testing, subagent walkthroughs, and screenshot captures are **not** necessary; visual UI verification will be performed manually by the user.
- **Client-Side Caching**: Utilize client-side caching (`localStorage`) where applicable to speed up page loads and reduce redundant API calls.
- **Semantic IDs**: Ensure interactive UI elements have unique, descriptive HTML IDs.

### Key Files & Modules
- [site_ui/cafe/](file:///d:/Git/Boardgame-Recommender/site_ui/cafe/): Cafe onboarding wizard, manager portal, mobile patron vibe check, and table QR code generator.
- [site_ui/vote/](file:///d:/Git/Boardgame-Recommender/site_ui/vote/): Real-time table voting and game night session portal.
- [site_ui/groups/](file:///d:/Git/Boardgame-Recommender/site_ui/groups/): Playgroup management.
- [site_ui/collection/](file:///d:/Git/Boardgame-Recommender/site_ui/collection/): BGG collection browser backed by the API proxy.
- [site_ui/recommender/](file:///d:/Git/Boardgame-Recommender/site_ui/recommender/): Primary recommender interface.
- [site_ui/settings/](file:///d:/Git/Boardgame-Recommender/site_ui/settings/): User scoring preferences and weight sliders.
- [site_ui/assets/js/utils.js](file:///d:/Git/Boardgame-Recommender/site_ui/assets/js/utils.js): Core client library (Cognito token refresh, API client, toast notifications).
- [site_ui/tests/](file:///d:/Git/Boardgame-Recommender/site_ui/tests/): Vitest frontend unit tests.
- [site_ui/_config.yml](file:///d:/Git/Boardgame-Recommender/site_ui/_config.yml) and [Gemfile](file:///d:/Git/Boardgame-Recommender/site_ui/Gemfile).
