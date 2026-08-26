# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

BackTest Studio is a credit strategy backtesting platform for Black Friday
credit-limit-increase (黑五大促提额) scenarios. It compares Champion /
Challenger / Beta credit strategies across five metric layers (L1-L5) on a
synthetic consumer-lending book, with a DeepSeek-backed AI assistant for
narrative analysis. UI copy is bilingual (zh/en) throughout — most
`desc_zh`/`desc_en` fields, i18n tables, and API `language` params exist in
pairs; keep both in sync when editing strings.

## Commands

### Backend (`backend/`)
```bash
cp .env.example .env               # add DEEPSEEK_API_KEY (optional — app runs without it)
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload      # http://localhost:8000, docs at /docs

pytest -q                          # full suite
pytest tests/test_metrics.py -q    # single file
pytest tests/test_metrics.py::test_name -q   # single test
RATE_LIMIT_ENABLED=0 pytest -q     # set automatically by tests/conftest.py
```

### Frontend (`frontend/`)
```bash
npm install
npm run dev          # http://localhost:5173, proxies /api -> localhost:8000 (see vite.config.ts)
npm run build        # tsc + vite build — this IS the type-check step; there is no separate typecheck script
npm run lint         # eslint .
npm test             # vitest run (unit tests: tests/unit/**, src/**/*.test.ts)
npx playwright test  # e2e (tests/e2e/**); requires backend + frontend running
```

CI (`.github/workflows/ci.yml`) runs backend `pytest -q` and frontend
`lint` → `build` → `test` (vitest) on every PR and push to `main`. Playwright
e2e is not run in CI.

## Architecture

### Backend: strategies operate on a shared `features` contract

The core abstraction is in `backend/app/strategies/contract.py`. A strategy
(built-in or user-uploaded) is just:

- `STRATEGY_META: dict` — name, version, role, `required_inputs` (logical
  feature names), `params` (name → `{type, default, min?, max?}`).
- `score(features: dict[str, np.ndarray], params) -> np.ndarray` — PD per row.
- `approve(features, pd_hat, params) -> np.ndarray` — boolean approval mask.

`DataView` resolves logical feature names to physical dataset columns via a
mapping (needed because uploaded CSVs won't have the built-in column names),
and separately resolves "role" columns (`outcome`, `score`, `gender`, ...)
that metrics need but strategies don't.

Two code paths produce a `StrategyResult` (approve_mask + pd_hat):
- **Built-in strategies** (`v2.2`, `v2.3`, `v2.4-Beta`, `v2.5-RC`, defined in
  `app/data/fixtures.py::STRATEGIES`) run in-process via
  `strategies/builtin_adapter.py`, which wraps the existing fixture math
  unchanged (bit-for-bit compatibility is a hard requirement there).
- **Uploaded/custom strategies** run in `strategies/sandbox.py` /
  `strategies/runner.py`: the code is `exec`'d in a *separate subprocess*
  with CPU/memory rlimits, a blocked `socket.socket`, and an import
  allowlist (`numpy`, `pandas`, `math`, `scipy`, etc). This is explicitly
  documented as demo-grade defence-in-depth, not a hardened sandbox — see the
  threat-model comment at the top of `runner.py` before changing it.

### The L1-L5 metric layers

Every backtest run computes five layers, each with its own KPIs and charts:
- **L1** Model quality — KS, AUC, lift@20, Brier, ROC, calibration, PSI trend, CSI
- **L2** Business value — approval rate, RAROC, avg profit, Pareto frontier, rejection reasons
- **L3** Risk — MOB12 bad rate, roll rates, vintage curves, FPD trend
- **L4** Swap-set analysis — double-approve/swap-in/swap-out/double-reject matrix vs champion, consistency, p-value
- **L5** Fairness — disparate-impact ratios by protected group, TPR gaps, SHAP-style feature importance

All metrics are **computed** from data, never hardcoded — the built-in
samples are synthetic books generated deterministically by
`app/data/fixtures.py::generate_synthetic_data` (seeded, capped at 80k rows,
LRU-cached in `services/metrics.py::get_sample_data`), so results are
reproducible and respond correctly to slicing.

Math for built-in strategies lives in `app/data/fixtures.py`
(`_compute_l1`..`_compute_l5`) and `app/services/{metrics,fairness,swap_set,stability}.py`.
Math for custom (uploaded strategy / uploaded dataset) runs lives in
`app/services/custom_metrics.py`. Both paths converge on the same
backend-shaped `layers` dict, keyed by strategy id, each holding `l1`..`l5`
plus special `_swap_chall_vs_champ` / `_swap_beta_vs_champ` / `_summary` keys.

`app/api/experiments.py::_reshape_layers` then transforms that
per-strategy/per-layer backend shape into the frontend's per-layer shape
(all strategies combined within each layer, e.g. `layers.l1.kpis` is a list
across champion/challenger/beta) — this reshape is the seam between backend
and frontend data models; when adding a new metric, wire it through fixtures
→ metrics service → `_reshape_layers` → frontend types (`frontend/src/types.ts`).

### Request flow

1. `POST /api/experiments/run` (or `/api/experiments/{id}/reslice`) picks
   built-in vs custom orchestration based on whether any `*_ref` field is set
   on `ExperimentConfig` (`_is_custom_config`), runs the CPU-bound backtest
   via `asyncio.to_thread` (so NumPy work doesn't block the event loop), and
   returns the frontend-shaped result.
2. Runs are cached in an in-memory dict (`_RUN_STORE`) as a hot read path,
   backed by SQLite (`app/db/repository.py`, plain `sqlite3`, WAL mode) so
   completed runs survive a restart — `rehydrate_run_store()` reloads them on
   startup (see `main.py` lifespan).
3. Custom strategy/dataset/column-mapping CRUD lives under `app/api/custom.py`;
   uploaded datasets are stored as parquet under `backend/data/uploads/`
   (capped at 80k rows / 25MB upload).
4. `app/api/ai.py` streams DeepSeek-backed SSE responses (`app/services/llm.py`)
   for: parsing natural-language config, per-layer analysis, chat, full report
   generation, and strategy comparison. All AI features degrade gracefully
   when `DEEPSEEK_API_KEY` is unset (`settings.llm_available`).
5. Per-IP rate limits (`app/ratelimit.py`, via slowapi): 10/min for full runs,
   30/min for reslicing, 20/min for AI streams. Disabled in tests via
   `RATE_LIMIT_ENABLED=0` (set in `tests/conftest.py` before app import).

### Frontend

React 18 + Vite + TypeScript, single-page-app-style screen switching in
`App.tsx` (no router) with `Screen` state: `config → execution → results`,
plus `history`, `list`, `strategies`, `datasets`. `api/client.ts` wraps
`fetch`, including a hand-rolled SSE reader (`backendStream`) that
translates backend event types (`thinking | result | reply | chunk | config`)
into UI callbacks. `screens/results/L1Panel.tsx`..`L5Panel.tsx` render the
five metric layers; `stratColors.ts` assigns consistent per-strategy chart
colors. i18n via `react-i18next`, dictionaries in `src/i18n/{en,zh}.ts`.

## Deployment

Two independent GitHub Actions on push to `main`
(`.github/workflows/deploy.yml`): frontend build+scp to Alibaba Cloud, and
backend SSH deploy (git reset --hard + systemd restart) — the backend job is
`continue-on-error: true` so a backend deploy failure never blocks/reddens
the frontend deploy. See `deploy/` for the systemd unit and nginx config.
