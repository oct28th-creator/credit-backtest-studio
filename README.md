# BackTest Studio

Credit strategy backtesting platform for Black Friday credit limit increase (黑五大促提额) scenarios.

## Quick Start

```bash
bash scripts/ctl.sh start     # background: API :8000, UI :5173
bash scripts/ctl.sh status    # who's running, and whether AI is connected
bash scripts/ctl.sh restart   # after editing .env or requirements.txt
bash scripts/ctl.sh stop
bash scripts/ctl.sh logs api  # or: logs web
bash scripts/ctl.sh doctor    # deps, ports, health — and whether the UI is
                              # about to render demo fixtures
bash scripts/ctl.sh test      # backend + frontend test suites
```

`start` refuses to bring up the UI until the API answers its health check: a UI
running against a dead backend silently renders demo fixtures, which is
indistinguishable from real results. Ports: `API_PORT=8001 WEB_PORT=5174`.

Foreground mode (Ctrl-C to stop) is still `bash scripts/dev.sh`.

Or by hand:

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

## Agent layer (P2)

The agent proposes and analyses; the metric layer computes; the guardrails
veto; a human approves. Nothing here decides credit policy.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/agent/tools` | Self-describing tool registry (JSON Schema) |
| POST | `/api/agent/tools/{name}` | Call one tool, optionally charged to a session |
| POST | `/api/agent/sessions` | Create a session with an experiment/LLM/wall-clock budget |
| GET | `/api/agent/sessions/{id}` | Budget usage and the runs it produced |
| POST | `/api/agent/investigate` | Run Designer → Executor → Analyst → Critic, collected |
| POST | `/api/agent/investigate/stream` | Same loop as SSE, one event per phase |

Tools: `list_strategies` `list_datasets` `submit_experiment` `sensitivity_scan`
`get_metrics` `compare_runs` `get_run_status` `search_experiments`
`annotate_run` `check_guardrails`.

Guardrails are deterministic and cannot be argued past: a disparate-impact
ratio under 0.80, an approved book under 500 accounts, or a protected
attribute used as a model input **blocks** the result; an insignificant
swap-set difference, a bad rate over the ceiling, or an extreme override
**warns**. A blocking finding forces the Critic verdict to `not_supported`
regardless of what the analysis said.

Budgets are enforced in the tool layer (not in the prompt), and a cache hit on
an identical manifest costs nothing. The whole loop runs without an API key —
each LLM step has a deterministic fallback.

```bash
curl -X POST localhost:8000/api/agent/investigate -H 'content-type: application/json' -d '{
  "goal": "v2.3 放宽通过率后 RAROC 是否还优于 v2.2",
  "base_config": {"champion": "v2.2", "challenger": "v2.3", "sample_id": "consumer_2024q1q2"},
  "budget": {"max_experiments": 4}
}'
```

## Simulation environments (P3)

A backtest is only as trustworthy as the world it assumes, so the world is now
an explicit, versioned object that travels with the run — including what it may
**not** be used to claim.

| Environment | Level | Confidence | What it is |
|---|---|---|---|
| `replay` | L0a | high | History replayed; every outcome known (previous default) |
| `reject_inference` | L0b | medium | Champion-rejected outcomes hidden, then estimated back |

`reject_inference` deliberately recreates the production condition — you only
observe repayment for accounts you approved — and then **checks the estimate
against the label it hid**. Every credit shop runs the estimate; almost none
report how wrong the method is. Here each run carries its own error bar:

```bash
curl -X POST localhost:8000/api/agent/tools/compare_ri_modes \
  -H 'content-type: application/json' \
  -d '{"args":{"config":{"champion":"v2.2","challenger":"v2.3","sample_id":"consumer_2024q1q2"}}}'
```

On the default book, `parceling` with the conventional ×2 penalty overestimates
the swap-in bad rate by ~83% relative — which the guardrails now **block**: a
conclusion resting on an estimate less accurate than the effect it reports is
not a conclusion. Ignoring rejects entirely (`ri_mode: none`) understates it by
the whole true rate.

Replication answers the other half: `replicate_across_seeds` reruns a config
across seeds and reports mean/CI plus whether the **ranking survives**
resampling. A ranking that flips across seeds forces the agent's verdict to
`not_supported` — deterministically, whatever the analysis claimed.

## Strategy sandbox (P6)

Uploaded strategy code runs in a subprocess that cannot reach the filesystem,
the network, or the interpreter's own internals:

- `__builtins__` is replaced with an allowlist dict — no `open`, `eval`,
  `exec`, `compile`, `getattr`, `globals`; `import` goes through a guard.
- The child closes `builtins.open` and `socket.socket`, and sets
  `RLIMIT_CPU` (6s soft / 10s hard), `RLIMIT_AS` (1 GiB), `RLIMIT_FSIZE` (4 MiB).
- Before a process is even spawned, `sandbox.gate_source()` walks the AST and
  rejects every dunder attribute (`__class__`, `__subclasses__`, `__globals__`)
  and every code-execution or namespace-reading name, with a reason.

`backend/tests/test_sandbox.py` is written as the attacks themselves — file
reads, file writes, sockets, `().__class__.__bases__[0].__subclasses__()`,
CPU spin, memory bomb. A passing test means the attack failed.

## MCP server (P6)

The 16-tool registry is exposed over MCP stdio, so Claude Code or Cowork can
drive experiments directly:

```bash
claude mcp add backtest -- backend/venv/bin/python -m app.mcp.server
```

The budget is per connection (`40 experiments / 0 LLM calls / 1 hour`) and is
enforced in the tool layer, not in the prompt. Errors are classified
(`budget_exceeded` / `invalid_request` / `not_found`) so an external agent can
act on them.

## Experiment history (P6)

Runs are immutable, so history is a tree, not a log:

| Endpoint | What it answers |
| --- | --- |
| `GET /api/history` | Every run, newest first, each with its guardrail verdict |
| `GET /api/history/trees` | Runs grouped by `root_run_id` — one question, every attempt |
| `GET /api/history/diff?a=&b=` | Two runs aligned by role, config diff above metric diff |

The diff refuses to crown a winner on approval rate: more approvals is better
or worse only together with the bad rate.

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
