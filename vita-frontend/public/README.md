# Vita — Health & Nutrition Frontend

Vanilla HTML/CSS/JS (no build step). Open `index.html` directly or use VS Code Live Server.

## Structure
- `index.html` — landing
- `login.html`, `register.html`, `onboarding.html`
- `dashboard.html`, `food-log.html`, `vitals.html`, `recommendations.html`, `profile.html`
- `styles/main.css` — design system + shared components
- `js/api.js` — fetch() wrapper (Bearer token, 401 redirect)
- `js/auth.js` — token/user storage, page guard
- `js/nav.js` — bottom-tab (mobile) + sidebar (desktop)
- `js/utils.js` — countUp, vitals color-coding, toast, theme
- `js/mock.js` — mock API payloads (swap for real fetch() calls)
- `js/dashboard.js`, `js/food-log.js`, `js/vitals.js`, `js/recommendations.js`, `js/profile.js`

## Swap mocks for real API
Each page script imports from `./mock.js`. Replace those calls with `api.get('/vitals/latest')` etc. from `./api.js` and set `BASE_URL` in `api.js`.

## CDN deps
- Chart.js — charts
- Lucide — icons
- Google Fonts — DM Sans + JetBrains Mono
