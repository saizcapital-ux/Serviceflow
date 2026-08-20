# The Reclaim Playbook — TradingView indicator

A Pine v5 overlay that runs the cheat-sheet on your live chart: auto S/R levels,
a flush→reclaim entry marker, the 6-point checklist scored in real time, a
regime/size read, and a hard NO-TRADE block over your 12–1pm ET hour.

## Install
1. Open **TradingView → Pine Editor** (bottom panel).
2. Paste the full contents of [`reclaim-playbook.pine`](./reclaim-playbook.pine).
3. Click **Add to chart**.
4. Best on a **1–5 min** chart of a ride-list name (SPCX / META / AAPL / TSLA).
5. (Optional) Right-click the ▲ signal → **Add alert** on “Reclaim entry (≥4/6)”
   so it pings you instead of you hunting.

## What each piece maps to
| On the chart | Cheat-sheet item |
|---|---|
| Gold horizontal lines | Your marked S/R levels |
| Blue line (fast MA) / gold line (slow MA) | Trend + trigger |
| ▲ RECLAIM marker + dashed stop/target | A valid flush→reclaim entry (≥4/6) |
| Red shaded band | 12–1pm ET — no-trade, verdict forced to NO-TRADE |
| Corner table | Live 6-point score, verdict, regime, max size, current R:R |

## The 6 checks (how they’re computed)
1. **At a level** — price within `nearMult × ATR` of the nearest pivot level
2. **Flush → reclaim** — bar wicked below support and closed back above it
3. **Fast MA reclaim** — close above the fast EMA and the EMA curling up
4. **Volume spike** — volume above `volMult ×` its average
5. **Clear runway** — room to the next level ≥ `runwayMult × ATR`
6. **R:R** — (target − entry) ÷ (entry − stop) ≥ your minimum (default 2:1)

Score **4+ and a reclaim → TAKE IT**. Under 4 → it’s a churn trade; wait.

## Tuning
- **Choppier names / higher timeframe:** raise *Pivot lookback* (fewer, stronger levels).
- **More/fewer signals:** lower/raise *Volume spike ×* and *Min reward:risk*.
- **Different bad hour or session:** edit the *No-trade window* (HHMM-HHMM, ET).
- **Regime sensitivity:** *ADX ≥* threshold — higher = only calls true trend days “TREND”.

> Signals confirm on bar close. Read the table on your entry bar, not intrabar.
> Decision support only — not investment advice. Validate on your own chart first.
