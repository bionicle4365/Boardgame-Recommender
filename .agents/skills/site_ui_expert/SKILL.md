---
name: Site UI Expert
description: Expert in HTML, Vanilla CSS, Jekyll configurations, Javascript, and responsive glassmorphic design systems.
---

## Guidelines for Frontend Development

### UI & Styling Standards
- **Aesthetic Principles**: Create premium, modern layouts with curated palettes, subtle micro-animations, smooth transitions, and glassmorphic elements.
- **Vanilla CSS**: Prioritize Vanilla CSS for styling. Do not use TailwindCSS unless explicitly instructed.
- **Responsive Layout**: Ensure grids, containers, and cards scale properly across mobile, tablet, and desktop viewports. Prevent horizontal overflows.
- **Loading UX**: Implement animated skeleton loading templates during async fetch operations.

### Local Development & Testing
- Run and test frontend changes locally using the Jekyll server (`bundle exec jekyll serve`).
- Verify standard UI elements have unique, descriptive HTML IDs for testing.
- Utilize client-side caching (`localStorage`) where applicable to speed up page loads.
- For any UI additions, changes, or deletions, perform browser testing using browser automation or subagents, capture screenshots of the changes during testing, and embed them in the walkthrough.md report.

### Key Files
- Frontend UI files under [site_ui/](file:///d:/Git/Boardgame-Recommender/site_ui/) (e.g. [_includes/](file:///d:/Git/Boardgame-Recommender/site_ui/_includes/), [_layouts/](file:///d:/Git/Boardgame-Recommender/site_ui/_layouts/), [assets/](file:///d:/Git/Boardgame-Recommender/site_ui/assets/)).
- [site_ui/_config.yml](file:///d:/Git/Boardgame-Recommender/site_ui/_config.yml) and [Gemfile](file:///d:/Git/Boardgame-Recommender/site_ui/Gemfile).
