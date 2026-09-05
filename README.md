# BackTest Studio

Credit strategy backtesting platform for Black Friday credit limit increase (黑五大促提额) scenarios.

## Quick Start

### Backend
```bash
cd backend
cp .env.example .env
# Add your DEEPSEEK_API_KEY to .env
pip install -r requirements.txt
uvicorn app.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## Stack
- **Frontend**: React 18 + Vite + TypeScript + react-i18next
- **Backend**: FastAPI (Python 3.11) + numpy/scipy/sklearn
- **AI**: DeepSeek API (streaming + thinking blocks)
- **Charts**: Chart.js 4

## Environment Variables
```env
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
CORS_ORIGINS=http://localhost:5173,http://47.82.160.74
# Optional shared-secret auth (empty = disabled). When set, every /api route
# requires this token. Frontend must then be built with the same value:
#   VITE_API_TOKEN=<same value>
APP_API_TOKEN=
```

## Strategies (Black Friday Credit Limit Increase)

All figures below are **computed** from the synthetic book (≈80k records), not
hardcoded metric overrides. The per-strategy approval rate is a calibration
target for the synthetic demo book (configurable via `PD_TARGET_APPROVAL_RATES`),
applied through each strategy's own model-score cutoff. Each strategy approves the lowest-risk applicants by its **own model
score** (a calibrated PD cutoff) subject to hard policy gates (DTI cap,
zero-delinquency over its MOB window, and v2.4-Beta's behaviour/thin-file gate).
Because the models rank applicants differently, the swap-set analysis shows real
two-way swap-in / swap-out.

| Version | Role | Approval | Bad Rate (MOB12) | RAROC | Note |
|---------|------|----------|------------------|-------|------|
| v2.2 | Champion (基线) | 23% | 1.7% | 20% | Conservative baseline |
| v2.3 | Challenger (挑战者) | 44% | 1.7% | **24%** | Best risk-adjusted return |
| v2.4-Beta | Beta | 66% | 3.6% | 21% | ⚠️ 18-25 客群 DI ≈ 0.53 (合规预警) |
| v2.5-RC | Beta RC | 49% | 2.3% | 23% | Graph-network anti-fraud |

Metrics respond to slicing — e.g. filtering to the 18-25 cohort drops v2.4-Beta
approval from 66% to ~37%, surfacing its disparate-impact issue; gender (not a
model input) leaves approval essentially unchanged.

## Agentic experiment foundations (P1)

Runs are immutable and content-addressed, so many of them can be generated
programmatically and still be citable as evidence. See
[docs/AGENTIC_UPGRADE_PLAN.md](docs/AGENTIC_UPGRADE_PLAN.md) for the full design.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/experiments/run` | Synchronous backtest (interactive path, unchanged) |
| POST | `/api/experiments/submit` | Queue a run; 202 with `run_id`, `manifest_sha`, `identical_prior_runs` |
| GET | `/api/experiments/jobs` | Lifecycle list (`queued`/`running`/`succeeded`/`failed`/`cancelled`) |
| GET | `/api/experiments/{id}/status` | Poll one run |
| POST | `/api/experiments/{id}/cancel` | Cancel an in-flight run |
| POST | `/api/experiments/{id}/reslice` | Derive a **new** run (never overwrites the parent) |
| GET | `/api/experiments/{id}/manifest` | Reproducibility document |
| GET | `/api/experiments/{id}/lineage` | Every run sharing the same root |
| POST | `/api/experiments/{id}/annotate` | Record hypothesis / conclusion / tags |

`ExperimentConfig` gained three optional fields — all backward compatible:

```jsonc
{
  "seed": 42,
  "policy_overrides": { "v2.3": { "target_approval_rate": 0.55, "dti_limit": 0.70 } },
  "param_overrides":  { "custom:abc123": { "cutoff": 0.08 } }
}
```

Built-in knobs are whitelisted (`target_approval_rate`, `dti_limit`, `mob_months`,
`mob_dpd_max`, `score_cutoff`, `limit_increase_min/max`): a sweep can move a
threshold, it cannot redefine a strategy.

## Deployment (Alibaba Cloud)
```bash
# One-time server setup — either run locally:
ssh root@47.82.160.74 'bash -s' < deploy/server-setup.sh
# …or trigger the "Setup Server" GitHub Actions workflow (workflow_dispatch),
# which runs the same script over SSH using the repository secrets.

# Subsequent deploys happen automatically via GitHub Actions on push to main
```

## Testing
```bash
# Backend
cd backend && pytest tests/ -v

# Frontend unit tests
cd frontend && npm test

# Frontend E2E
cd frontend && npx playwright test
```

## GitHub Actions
Set these secrets in the repository settings:
- `SERVER_HOST`: `47.82.160.74`
- `SERVER_USER`: `root`
- `SERVER_SSH_KEY`: your private SSH key content, **or** `SERVER_PASSWORD`: the server's root password (key wins if both are set)
