# Repository Guidelines

## Project Structure & Module Organization
This repo is a standalone extraction of the theme picker from `daily_stock_analysis`, split into a Python service at the root and a Vite React client in `web/`. `server.py` exposes the FastAPI app, while `main.py` launches backend-only, frontend-only, or combined local development. Under `src/`, `api/` handles HTTP schemas and endpoints, `application/` owns scan orchestration and async task lifecycle, `core/` contains the theme alert pipeline, `infrastructure/` implements persistence, runtime config, board resolution, event scanning, and signal evaluation, and `data_provider/` encapsulates market/news source adapters. SQLite task history lives in `data/` and feeds the API history and retry endpoints.

## Build, Test, and Development Commands
Install backend dependencies with `pip install -e .` or `pip install -r requirements.txt`. Run the API with `python main.py --serve`, the frontend dev server with `python main.py --serve-web`, or both with `python main.py --serve-all`. A direct backend alternative is `uvicorn server:app --host 127.0.0.1 --port 8765`. In `web/`, use `npm run dev`, `npm run build`, `npm run lint`, `npm run test`, and `npm run preview`. Run a single frontend test with `npm run test -- src/pages/__tests__/ThemeStockPickerPage.test.tsx`.

## Coding Style & Naming Conventions
Python code uses a package-style layout under `src/`; follow the existing naming pattern such as `*_service.py`, `*_fetcher.py`, and schema objects in `api/schemas.py`. On the frontend, ESLint is enforced through `web/eslint.config.js` with `@eslint/js`, `typescript-eslint`, `react-hooks`, and `react-refresh`. TypeScript is strict in `web/tsconfig.app.json`: `strict`, `noUnusedLocals`, and `noUnusedParameters` are enabled, so keep types explicit and remove dead props or imports promptly.

## Testing Guidelines
Frontend tests run on Vitest with `jsdom` and shared setup from `web/src/setupTests.ts`; current coverage is centered on page-level behavior in `web/src/pages/__tests__`. `npm run test:smoke` is wired to Playwright, but no tracked `playwright.config.*` or `e2e/` specs are present yet. No backend pytest suite is checked in even though `pytest` is listed in the Python dev extras.

## Commit & Pull Request Guidelines
Git history currently contains only `first commit`, so there is not yet a mature commit taxonomy to inherit. Keep commit subjects short and plain, and describe the concrete area changed, especially when touching both root Python code and `web/`. No pull request template or repo-local agent rule files were found, so PR descriptions should call out affected commands, API endpoints, and any task-history or data migration impact.
