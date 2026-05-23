# BackTest Studio

Credit strategy backtesting platform for Black Friday credit limit increase (黑五大促提额) scenarios.

## Quick Start

### Backend
```bash
cd app/backend
cp .env.example .env
# Add your DEEPSEEK_API_KEY to .env
pip install -r requirements.txt
uvicorn app.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

### Frontend
```bash
cd app/frontend
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
CORS_ORIGINS=http://localhost:5173,http://8.217.224.101
```

## Strategies (Black Friday Credit Limit Increase)
| Version | Role | Approval | Bad Rate | RAROC |
|---------|------|----------|----------|-------|
| v2.2 | Champion (基线) | 28% | 1.8% | 18% |
| v2.3 | Challenger (挑战者) | 38% | 2.4% | **22%** |
| v2.4-Beta | Beta | 45% | 3.2% | 16% ⚠️ DI=0.77 |
| v2.5-RC | Beta RC | 40% | 2.6% | 20% |

## Deployment (Alibaba Cloud)
```bash
# One-time server setup
ssh root@8.217.224.101 'bash -s' < app/deploy/server-setup.sh

# Subsequent deploys happen automatically via GitHub Actions on push to main
```

## Testing
```bash
# Backend
cd app/backend && pytest tests/ -v

# Frontend unit tests
cd app/frontend && npm test

# Frontend E2E
cd app/frontend && npx playwright test
```

## GitHub Actions
Set these secrets in the repository settings:
- `SERVER_HOST`: `8.217.224.101`
- `SERVER_USER`: `root`
- `SERVER_SSH_KEY`: your private SSH key content
