# Frontend — AI 项目管理 Agent

Next.js (App Router) + TypeScript + Ant Design. The primary surface is a phone
browser or WeCom WebView, so every page is designed mobile-first and the desktop
view is the same layout in a centred container.

## Local development

```bash
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

Open <http://localhost:3000>. The landing page renders the backend readiness
report, which doubles as a connectivity check.

## Layout

| Path                   | Responsibility                                             |
| ---------------------- | ---------------------------------------------------------- |
| `app/`                 | App Router routes, layouts and global CSS                   |
| `components/`          | Reusable UI; `providers/` holds context providers           |
| `hooks/`               | Client-side React hooks                                     |
| `lib/`                 | Framework-agnostic helpers (`env`, `http`, `theme`)          |
| `services/`            | One module per backend resource; the only place calling `/api` |
| `types/`               | Shared response and domain types                            |
| `public/`              | Static assets                                               |

## Conventions

- Fetch data in server components, then pass it down as props. Client components
  ask for fresh data with `useRefresh()` (a `router.refresh()` wrapper) rather
  than duplicating fetch logic.
- Never call `fetch` directly in feature code — go through `lib/http.ts` so base
  URL, timeouts and error shape stay consistent.
- Ant Design for desktop-leaning views, Ant Design Mobile for touch-first flows.
  Both need `"use client"`.

## Environment variables

| Variable                   | Used by                | Meaning                                                            |
| -------------------------- | ---------------------- | ------------------------------------------------------------------ |
| `NEXT_PUBLIC_API_BASE_URL` | browser (build-time)   | API base URL. Empty = same origin (behind Nginx).                  |
| `INTERNAL_API_BASE_URL`    | server components      | Direct backend URL inside Docker, e.g. `http://backend:8000`.       |
| `NEXT_PUBLIC_APP_NAME`     | browser                | Display name in the header and `<title>`.                           |

## Commands

```bash
npm run dev        # dev server on 0.0.0.0:3000
npm run build      # production build (standalone output)
npm run start      # serve the production build
npm run lint       # eslint
npm run typecheck  # tsc --noEmit
```
