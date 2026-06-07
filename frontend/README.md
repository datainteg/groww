# Frontend — AI Trading (React + TypeScript)

Mobile-first trading UI for the Groww AI trading backend. React 18 + Vite + TailwindCSS +
Zustand, with `lightweight-charts` for candles.

## Setup & run
```bash
npm install
npm run dev      # http://localhost:3000
npm run build    # type-check (tsc) + production build to dist/
```

Configure the API base with an env var (defaults to `http://localhost:5000/api`):
```
# .env.local
VITE_API_URL=http://localhost:5000/api
```

## UI / UX
- **Mobile-app shell:** off-canvas drawer sidebar + bottom tab bar + responsive layout; tables
  scroll horizontally on small screens.
- **Groww light theme** (green `#00d09c`), light-first with a dark toggle.
- **Daily token banner:** when the Groww token is stale (expires ~6 AM IST) a banner shows
  "showing older data — update" and auto-opens a reconnect modal.
- **First-login gate:** forces a password change for the default account.
- **Auth:** JWT in localStorage; axios interceptor does a single refresh-retry before logout.

## Structure
```
src/
  api/         axios instance (interceptors) + per-domain API modules
  store/       Zustand stores (auth, market, strategy, trade, ui, direction)
  pages/       Dashboard, Signals, Trades, Strategy, Charts, Settings, Profile, Login
  components/  layout (Sidebar, BottomNav, Header), common (banners, modals, toast), ...
  types/       shared TypeScript types
  config/      app config + polling intervals
```

## Notes
- Decisions are read per-symbol from a `decisions[symbol]` map (no cross-page signal mixups).
- Charts discard in-flight responses after a symbol switch (no wrong-symbol candles).
- All data is **real** (from the backend/Groww) — there is no mock data.
