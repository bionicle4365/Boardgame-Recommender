# Site UI Rules (`site_ui/`)

- **Vanilla CSS & Design Tokens**: Use Vanilla CSS and reuse custom properties from `site_ui/assets/css/design-system.css` (support both light and `html[data-theme="dark"]`). Do not introduce TailwindCSS unless explicitly instructed.
- **Semantic IDs & Modular JS**: Keep page scripts modular under `site_ui/assets/js/` and ensure interactive elements have unique, descriptive HTML `id` attributes.
- **Contract Sync**: Check `docs/contracts/schemas_and_routes.json` for backend API route paths and authentication requirements (`public` vs `cognito_jwt`).
- **Verification Policy**: Always run `npm --prefix site_ui test` (`vitest run`) to verify frontend behavior; automated browser/visual verification is not needed unless explicitly requested.
