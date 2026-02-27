# NSEScan — Indian Stock Market Technical Scanner

A cloud-deployable stock scanner for NSE-listed Indian equities,
powered by Yahoo Finance data via `yfinance`.

---

## Project Structure

```
trading-scanner/
├── backend/
│   ├── app.py                       Flask REST API
│   ├── requirements.txt             Python dependencies
│   ├── gunicorn.conf.py             Production server config
│   ├── runtime.txt                  Python version pin
│   ├── strategies/
│   │   ├── __init__.py              Strategy registry
│   │   ├── base.py                  Abstract base class
│   │   ├── rsi_oversold.py          RSI(14) < 35
│   │   ├── macd_crossover.py        MACD bullish crossover
│   │   ├── golden_cross.py          50 SMA crosses 200 SMA
│   │   ├── breakout.py              Near 52-week high
│   │   ├── volume_surge.py          3× average volume spike
│   │   └── ema_pullback.py          Pullback to 20 EMA in uptrend
│   └── universe/
│       ├── __init__.py
│       └── india_stocks.py          NSE tickers by index
├── frontend/
│   └── index.html                   Single-file frontend (no build step)
├── docs/                            (for your own notes)
├── render.yaml                      Render.com backend deployment
├── netlify.toml                     Netlify frontend deployment
├── Procfile                         Heroku/Railway alternative
├── .gitignore
└── README.md
```

---

## Strategies

| Strategy                | Logic                                                     |
|-------------------------|-----------------------------------------------------------|
| RSI Oversold            | RSI(14) < 35 — potential mean-reversion bounce            |
| MACD Bullish Crossover  | MACD crossed above Signal line in last 3 bars             |
| Golden Cross (50/200)   | 50-day SMA crossed above 200-day SMA in last 5 bars       |
| 52-Week High Breakout   | Price within 2% of 52-week high                           |
| Volume Surge            | Volume ≥ 3× 20-day average + price move ≥ 1.5%           |
| EMA Pullback            | Uptrending stock (price > 50 EMA) touching 20 EMA        |

## Stock Universes

| Universe        | Stocks |
|-----------------|--------|
| Nifty 50        | 50     |
| Nifty Next 50   | 50     |
| Nifty Midcap 50 | 50     |
| Nifty Bank      | 14     |
| Nifty IT        | 15     |
| Nifty Pharma    | 15     |
| Nifty FMCG      | 14     |

---

## Local Development

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
# API now runs at http://localhost:5000
```

### 2. Frontend

Open `frontend/index.html` directly in your browser.
The frontend auto-detects `localhost` and points to `localhost:5000`.

### Test the API manually

```bash
# Health check
curl http://localhost:5000/api/health

# List strategies
curl http://localhost:5000/api/strategies

# Run a scan
curl -X POST http://localhost:5000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"strategy": "RSI Oversold", "universe": "Nifty 50"}'
```

---

## ☁ Cloud Deployment (Step-by-Step)

### Step 1 — Push to GitHub

```bash
cd trading-scanner
git init
git add .
git commit -m "feat: initial NSEScan"
git remote add origin https://github.com/YOUR_USER/trading-scanner.git
git push -u origin main
```

---

### Step 2 — Deploy Backend on Render (Free)

1. Go to [render.com](https://render.com) → Sign Up → **New → Web Service**
2. Connect your GitHub repo
3. Render auto-reads `render.yaml`. Verify settings:
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app -c gunicorn.conf.py`
4. Click **Create Web Service**
5. Wait ~3 minutes for the build. Copy your URL, e.g.:
   ```
   https://nse-scanner-api.onrender.com
   ```

> ⚠️ Free Render services spin down after 15 min of inactivity.
> First request after idle may take ~30 seconds. Upgrade to Starter ($7/mo) to avoid this.

---

### Step 3 — Update Frontend with your Backend URL

Edit `frontend/index.html`, find this line (around line 380):

```javascript
: 'https://YOUR-BACKEND.onrender.com';
```

Replace with your actual Render URL:

```javascript
: 'https://nse-scanner-api.onrender.com';
```

Then commit and push:

```bash
git add frontend/index.html
git commit -m "fix: set production backend URL"
git push
```

---

### Step 4 — Deploy Frontend on Netlify (Free)

**Option A — Drag & Drop (30 seconds)**
1. Go to [netlify.com](https://netlify.com) → Log in
2. Drag the `frontend/` folder into the Netlify dashboard
3. Done! You get a URL like `https://nse-scanner-xyz.netlify.app`

**Option B — Git Deploy (auto-updates on push)**
1. Netlify → **Add new site → Import from Git**
2. Choose GitHub → select your repo
3. Settings (auto-detected from `netlify.toml`):
   - Publish directory: `frontend`
4. Click **Deploy**

---

### Alternative: Railway (backend + frontend in one)

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

---

## API Reference

| Endpoint           | Method | Description                         |
|--------------------|--------|-------------------------------------|
| `GET  /api/health` | GET    | Health check                        |
| `GET  /api/strategies` | GET | All strategies + descriptions      |
| `GET  /api/universes`  | GET | All universes + stock counts        |
| `POST /api/scan`   | POST   | Run a strategy scan                 |

### POST /api/scan

**Request body:**
```json
{
  "strategy": "RSI Oversold",
  "universe": "Nifty 50"
}
```

**Response:**
```json
{
  "strategy": "RSI Oversold",
  "universe": "Nifty 50",
  "total_scanned": 50,
  "matches": 3,
  "results": [
    {
      "ticker": "TATASTEEL",
      "full_ticker": "TATASTEEL.NS",
      "price": 142.55,
      "change_pct": -1.8,
      "rsi": 27.4,
      "signal": "RSI Oversold @ 27.4",
      "strength": "Strong",
      "metric_label": "RSI(14)",
      "metric_value": "27.4"
    }
  ]
}
```

---

## Adding a New Strategy

1. Create `backend/strategies/my_strategy.py`:

```python
from .base import BaseStrategy

class MyStrategy(BaseStrategy):
    name = "My Strategy Name"
    description = "One line description of what this strategy finds."

    def scan(self, ticker: str, data) -> dict | None:
        close = data["Close"].squeeze()
        # ... your logic ...
        if condition_met:
            return {
                "ticker":        self._clean(ticker),
                "full_ticker":   ticker,
                "price":         round(float(close.iloc[-1]), 2),
                "change_pct":    self._price_change(close),
                "signal":        "My Signal Description",
                "strength":      "Strong",      # or "Moderate"
                "metric_label":  "My Metric",
                "metric_value":  "42",
            }
        return None
```

2. Register in `backend/strategies/__init__.py`:

```python
from .my_strategy import MyStrategy

STRATEGIES = {
    s.name: s for s in [
        ...
        MyStrategy(),   # ← add here
    ]
}
```

That's it — the frontend and API pick it up automatically.

---

## Disclaimer

For **educational and informational purposes only**.
This is not financial advice. Always do your own research before investing.