# Trading Journal

A personal trading journal that **plugs into your Robinhood account**,
automatically loads every closed trade, and plots each one on a price chart —
**exactly where you took it**. Green triangles are winners, red are losers,
sized by dollar impact.

It's a single static page (no build step, no server) driven by one data file.

![overview](docs/preview.png)

## What's inside

| File | Purpose |
|------|---------|
| `index.html` | The journal UI |
| `styles.css` | Theme-aware design system (light + dark) |
| `app.js` | Charts, stats, trade log (vanilla JS + inline SVG) |
| `data.js` | Your trades + price history (generated) |
| `import_robinhood.py` | Pulls fresh data from Robinhood → regenerates `data.js` |

## Features

- **Equity curve** — cumulative realized P&L across every closed trade.
- **Daily P&L** — net profit per trading day.
- **"Where I took my trades"** — candlestick chart per symbol with a marker on
  the underlying price at each trade. Toggle **Intraday** for today's SPY fills
  on 5-minute bars at their exact times.
- **KPIs** — net P&L, win rate, profit factor, avg win/loss, best day, best &
  worst trade.
- **P&L by symbol** and a **sortable, filterable trade log**.
- Light/dark theme, fully responsive.

## View it

Just open `index.html` in a browser, or serve the folder:

```bash
cd trading-journal
python -m http.server 5500   # then open http://localhost:5500
```

The repo ships with a **real snapshot** of data, so it works immediately.

## Refresh with your live account

```bash
pip install robin_stocks
python import_robinhood.py          # prompts for email / password / MFA
```

The importer:

1. Logs into Robinhood (`robin_stocks`).
2. Pulls all **filled** stock and option orders.
3. Reconstructs **closed round-trip trades** (FIFO matching) with realized P&L.
4. Downloads daily price history for every symbol you traded, plus today's SPY
   5-minute bars.
5. Writes `data.js`. Reload the page — the whole journal updates.

Credentials can be passed via environment variables instead of prompts:

```bash
export RH_USERNAME="you@email.com"
export RH_PASSWORD="…"
export RH_MFA="123456"     # optional TOTP code
python import_robinhood.py
```

Nothing is uploaded or stored anywhere — the only output is your local
`data.js`. Robinhood has no official public API; `robin_stocks` uses the same
private endpoints the mobile app does, so treat it accordingly.

## Notes

- Figures are **informational only** — not tax or investment advice.
- Option `Exec $` in the trade log is premium per contract × 100; the marker on
  the chart sits on the **underlying's** price, which is where the trade
  actually happened in the market.
- Symbols without downloadable price history (e.g. index options like SPXW)
  still appear in the stats and trade log, just not on the price chart.
