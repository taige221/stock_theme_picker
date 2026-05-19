# Repository Guidelines

## Project Structure & Module Organization
Standalone theme-based stock picker: Python FastAPI backend at root + Vite React frontend in `web/`. `server.py` exposes the FastAPI app; `main.py` launches backend (`--serve`), frontend (`--serve-web`), or both (`--serve-all`). Under `src/`:
- `api/` — HTTP route handlers and Pydantic request/response schemas
- `application/` — service layer: scan orchestration, task lifecycle, stock queries, alerts, deep analysis
- `core/` — theme alert pipeline (main scan flow)
- `infrastructure/` — persistence, board resolution, event scanning, signal evaluation, daily bar caching
- `data_provider/` — market/news source adapters (akshare, efinance, yfinance, baostock, pytdx, longbridge, tushare, tickflow)
- `domain/` — domain models

SQLite databases live in `data/`. State management on frontend uses Zustand; routing via react-router-dom; charts via Recharts.

## Build, Test, and Development Commands
```bash
# Backend
pip install -e .                  # or: pip install -r requirements.txt
python main.py --serve            # API only at http://127.0.0.1:8765
python main.py --serve-web        # frontend only at http://127.0.0.1:5183/theme-picker
python main.py --serve-all        # both
uvicorn server:app --host 127.0.0.1 --port 8765  # direct alternative

# Frontend (from web/)
npm install
npm run dev
npm run build                     # tsc -b && vite build
npm run lint                      # eslint .
npm run test                      # vitest run
npm run test -- path/to/test.tsx  # single test
```

No backend pytest suite exists yet; `pytest` is in dev extras but no test directory is checked in.

## Coding Style & Naming Conventions
**Python:** package layout under `src/`, mapped as `theme_picker.*` via setuptools. Services are `*_service.py`, data adapters are `*_fetcher.py`, schemas in `api/schemas.py`. Python 3.11+ required.

**Frontend:** TypeScript strict mode (`strict`, `noUnusedLocals`, `noUnusedParameters` in `tsconfig.app.json`). ESLint enforced via `web/eslint.config.js` with `@eslint/js`, `typescript-eslint`, `react-hooks`, `react-refresh`. Styling with Tailwind CSS v4 + `tailwind-merge` + `clsx`. React 19 with React Compiler (`babel-plugin-react-compiler`).

## Testing Guidelines
Frontend tests: Vitest + jsdom, setup in `web/src/setupTests.ts`, test files in `web/src/pages/__tests__/`. Playwright is wired (`npm run test:smoke`) but no e2e specs exist yet.

## Commit & Pull Request Guidelines
Use conventional commits: `feat:`, `fix:`, with a short subject. When changes span both Python backend and `web/` frontend, note both areas. PR descriptions should call out affected API endpoints and any data migration impact.
