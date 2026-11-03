# Frontend Developer Guide

The dashboard (`frontend/`) is a React 19 + TypeScript single-page application built with Vite. It is a pure API
client: it holds no business rules that the server does not also enforce, and every number it shows comes from the
API. Quick start, scripts and environment variables are in `frontend/README.md`.

## 1. Stack

| Concern | Choice | Notes |
| --- | --- | --- |
| UI | React 19, TypeScript 5.9 (strict, `noUncheckedIndexedAccess`) | No UI framework; components in `src/components` |
| Routing | React Router 8 (declarative `<Routes>`) | `useTransitions={false}`: URL-bound inputs must update synchronously |
| Server state | TanStack Query 5 | Query keys centralised in `src/services/queryKeys.ts` |
| HTTP | Axios | One instance in `src/services/apiClient.ts` |
| Charts | Plotly (basic bundle: bar, line, pie) | Loaded on demand (separate ~380 KB gzip chunk); every chart has a data-table alternative |
| Styling | Plain CSS with custom properties | `src/styles/tokens.css` (light/dark tokens), `base.css`, `layout.css`, `components.css` |
| Tests | Vitest, Testing Library, jsdom | `npm test`; optional Playwright smoke test (`npm run e2e:smoke`) |

## 2. Project layout

```
src/
  main.tsx                providers: React Query, theme, toasts, router, auth
  App.tsx                 route map with role guards
  types/api.generated.ts  generated from docs/api/openapi.json — do not edit
  types/api.ts            readable aliases (Dataset, AnalysisJob, PredictionDetail, …) and enum lists
  services/               apiClient (tokens, refresh, errors, downloads) + one module per API area
  features/
    auth/                 AuthContext (session), RequireAuth, RequireRole, roles
    theme/                ThemeProvider (light/dark/system)
    analysis/             new-job dialog, quick analysis, job summary, mode labels
    alerts/               explanation view, review panel
    datasets/             validation-report renderer
    models/               metrics renderer, experiment viewer
    admin/                user dialogs
  pages/                  one component per route (13 pages + not-found)
  components/             Button, Card, DataTable, Pagination, Modal, ConfirmDialog, FormFields, Badge,
                          Chart, ConfusionMatrix, Tabs, Toast, States (loading/empty/error), FileDropZone, …
  hooks/                  useSearchState (URL state), useDebouncedValue, usePageTitle, useServerLimits
  utils/                  formatting, error messages, CSV parsing for previews, downloads, time windows
  test/                   setup (jest-dom, Plotly mock), fixtures, render helper
```

## 3. Pages and routes

| Route | Page | Roles |
| --- | --- | --- |
| `/login` | Sign in | public |
| `/` | Security overview (KPIs, trends, risk bands, labels; recent alerts and jobs for analysts) | all |
| `/datasets` | Dataset management (filter, details with validation report, delete, analyze) | admin, analyst |
| `/datasets/upload` | Upload with local preview, preliminary schema check and server validation | admin, analyst |
| `/analyses` | Analysis jobs (new job dialog, cancel) and Quick analysis tab | admin, analyst |
| `/analyses/:jobId` | Prediction results: job status, summary, evaluation, filterable predictions, CSV/JSON export | admin, analyst |
| `/alerts` | Threat/alert management: severity/status/label/IP/date filters, export | admin, analyst |
| `/alerts/:alertId`, `/predictions/:predictionId` | Alert details: scores, explanation, risk breakdown, context, reviews | admin, analyst |
| `/models` | Model information: versions, metrics, verification and status changes (admin), experiments | all (viewers: approved only) |
| `/analytics` | Analytics and reports: summary report, trends, model metrics, report downloads | all |
| `/admin/users` | User management | admin |
| `/admin/audit-logs` | Audit logs | admin |
| `/settings` | Profile, password, theme, system information, risk policy, health | all |

Role guards (`RequireRole`) mirror the API's matrix so users are not offered actions they cannot perform; the API
still authorizes every request.

## 4. Data flow

* **Types** are generated from the OpenAPI document: after any API change run `npm run generate:api`, then
  `npm run typecheck` to find every affected component.
* **Services** (`src/services/*.ts`) are thin typed functions around Axios — components never call Axios directly.
* **Queries** use keys from `queryKeys.ts`; mutations invalidate the narrowest affected prefix (for example a review
  invalidates the alert lists and the prediction detail).
* **URL state**: filters, sorting, paging and tabs live in the query string via `useSearchState`, so views are
  bookmarkable and survive reloads. Free-text inputs keep local state and update the URL debounced.
* **Polling**: job lists and job details poll every 2–3 s only while a job is queued, validating or running.

## 5. Session handling (`features/auth/AuthContext.tsx`, `services/apiClient.ts`)

1. On load the app calls `POST /auth/refresh`; the HttpOnly refresh cookie restores the session silently.
2. The access token is kept **in memory only** (never in `localStorage`/`sessionStorage`) and attached by an Axios
   interceptor.
3. A timer refreshes the token one minute before it expires. A `401` triggers one shared ("single-flight") refresh
   and a single retry of the failed request; if the refresh fails the user returns to the sign-in page with a
   "session expired" notice.
4. Sign-out calls `POST /auth/logout` (revokes every token of the user) and clears the query cache.
5. Changing the password ends the session locally because the server revokes all tokens.

## 6. Errors and messages

All failures become `ApiError` (`status`, `code`, `message`, `details`, `requestId`). `utils/errors.ts` maps codes to
friendly text (`model_unavailable`, `rate_limited` with retry time, network errors), field errors for forms
(`validation_error`, `weak_password`) and record-level problems for quick analysis. Error states show the request ID
so support can find the matching server log line.

## 7. Score semantics in the UI

Follow these rules in any new view (see `components/ScoreSemantics.tsx`):

* Show `probability` only when `scores_calibrated` is true; otherwise show "n/a" and label the classifier score as
  uncalibrated.
* Label the risk score as a policy score (0–100), never as a probability.
* Anomaly scores mean "unusual", not "malicious".
* Present explanations with their disclaimer; they describe model behaviour, not causality.
* Never compute, estimate or fill in metrics in the browser; render what the API returns and show "—" for missing values.

## 8. Accessibility and UX conventions

* Every input has a visible label (`TextField`, `SelectField`, `TextAreaField` wire `aria-describedby` for hints
  and errors).
* `DataTable`: sortable headers expose `aria-sort`; clickable rows are focusable and open with Enter/Space.
* Dialogs trap focus, close with Escape and restore focus; tabs support arrow keys.
* Charts expose `role="img"` with a label and a "Show data table" alternative.
* Colour is never the only signal (badges carry text); both themes use the same semantic tokens.

## 9. Security practices

* Render untrusted data as text only — ESLint forbids `dangerouslySetInnerHTML`.
* Uploaded files are previewed by reading only the first 64 KB as text; nothing is executed or uploaded before the
  user confirms.
* Post-login redirects accept same-origin relative paths only (`safeRedirect`).
* Downloads use Blob object URLs with sanitised file names.
* Only `VITE_*` variables reach the bundle; never place secrets in frontend environment files.

## 10. Adding a page

1. Add service functions and, if needed, query keys.
2. Create `src/pages/MyPage.tsx` using `PageHeader`, `Card`, `DataTable`, `Pagination` and the state components.
3. Register the route in `App.tsx` with the right role guard and add a navigation entry in `layouts/AppLayout.tsx`.
4. Write a test next to the page using `renderWithProviders` from `src/test/render.tsx` and mocked services.
5. Run `npm run typecheck && npm run lint && npm test && npm run build`.
