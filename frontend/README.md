# CyberSentinel frontend

React 19 + TypeScript single-page application for the CyberSentinel API. It is a client only: every number on
screen comes from the API, and the API decides what each user may see.

See [`docs/frontend_developer_guide.md`](../docs/frontend_developer_guide.md) for architecture, conventions and how
to add a page.

## Requirements

- Node.js **22.22 or newer** (enforced by `engine-strict`)
- A running CyberSentinel API (see the root README). The SPA does not work without it.

## Install and run

```bash
cd frontend
npm ci
cp .env.example .env.local      # optional; defaults work with the dev proxy
npm run dev                     # http://localhost:5173
```

During development the SPA calls `/api/v1` on its own origin and Vite proxies those requests to
`VITE_DEV_API_PROXY` (default `http://127.0.0.1:8000`). Keeping the API same-origin means the HttpOnly refresh
cookie stays first-party; the backend's `CORS_ORIGINS` must contain `http://localhost:5173` (the default) because
the refresh and logout endpoints check the `Origin` header.

For local HTTP development set `COOKIE_SECURE=false` in `backend/.env`. Some browsers (notably Safari) refuse
`Secure` cookies over plain `http://localhost`, which makes the session disappear on reload.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server with the API proxy |
| `npm run build` | Type-check (`tsc -b`) and build static files into `dist/` |
| `npm run preview` | Serve `dist/` locally (no API proxy — use a reverse proxy, see below) |
| `npm run typecheck` | TypeScript only |
| `npm run lint` | ESLint (flat config; bans `dangerouslySetInnerHTML`) |
| `npm test` | Vitest + Testing Library (jsdom) |
| `npm run generate:api` | Regenerate `src/types/api.generated.ts` from `docs/api/openapi.json` |

After changing the API, export the schema (`python -m app.cli export-openapi` in `backend/`), run
`npm run generate:api`, then `npm run typecheck`; type errors show every place the UI must follow the change.

## Configuration

Only `VITE_*` variables reach the browser, so **never put secrets in frontend environment files**.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | API base URL as seen by the browser. Keep the default behind a reverse proxy. |
| `VITE_DEV_API_PROXY` | `http://127.0.0.1:8000` | Dev server only: where `/api` is proxied. |

## Serving a production build

`npm run build` produces static files in `dist/`. Serve them from any static web server and route `/api/` to the
FastAPI process on the same origin, with an SPA fallback (unknown paths → `index.html`). Add the origin to the
backend's `CORS_ORIGINS`, enable `COOKIE_SECURE=true` and serve over HTTPS. Deployment itself is outside the scope
of this repository.

## Layout

```
src/
  main.tsx, App.tsx          entry point and route map
  services/                  Axios client (token handling, error normalization) and one module per API area
  types/                     generated OpenAPI types + named aliases (api.ts)
  features/                  auth (session, guards, roles), theme, analysis, alerts, datasets, models, admin
  pages/                     the 13 application pages + not-found
  components/                shared UI: tables, charts, dialogs, form fields, badges, states, toasts
  hooks/, utils/             URL-backed filters, formatting, CSV parsing for previews, downloads
  styles/                    design tokens (light/dark), base, layout and component CSS
  test/                      test setup, fixtures and render helper
```
