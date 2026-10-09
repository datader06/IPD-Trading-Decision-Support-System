# IPD Trading Desk (frontend)

React + TypeScript + Vite + Tailwind v4. Motion: Lenis (smooth scroll) driven by the GSAP ticker, GSAP ScrollTrigger, and components copied from
[React Bits](https://github.com/DavidHDev/react-bits) into `src/components/reactbits/` (MIT + Commons Clause, see that repo's LICENSE).

## Run

```bash
# 1. API (repo root). Wraps src/kite_client.py, read-only: instruments() and historical_data() only.
python3 -m venv api/.venv && api/.venv/bin/pip install -r api/requirements.txt
api/.venv/bin/uvicorn api.main:app --port 8000

# 2. Frontend
cd frontend && npm install && npm run dev      # http://localhost:5173, /api is proxied to :8000
```

Real prices need a Kite login (`python kite_login.py`, then restart the API). Without one the desk shows clearly labelled synthetic bars.
The access token never leaves the API process.

## Pages

- `/` overview: hero, pinned scroll walkthrough of the strategy, fixed-rule facts.
- `/desk` candlestick chart (15m / 60m / daily), trade-level calculator (same sizing as `src/candidates.py`), backtest baselines from `docs/STATUS.md`,
  and backtest trade lists from `results/**/*{combo}*final*.csv` when those files exist.
