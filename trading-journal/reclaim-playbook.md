# The Reclaim Playbook — TradingView indicator

A Pine v5 overlay that reads **four signals together** and scores a **LONG or
SHORT** live on your chart, then blocks your worst hour.

## The four signals
1. **9 / 21 EMA cross** — the trigger. Bull cross (9 over 21) = long trigger,
   bear cross = short trigger. Small △/▽ marks every cross; a filled ▲/▼ prints
   only when the cross also passes the checklist.
2. **Auto-anchored Volume Profile** — bias. The profile is drawn on the right
   (green above POC, red below, gold = POC line). **Price above POC = bullish,
   below POC = bearish.** Anchor to the **session** open or the **last swing**.
3. **VWAP position** — above VWAP = long bias, below = short bias. A valid long
   won’t fire below VWAP, and a short won’t fire above it.
4. **Support / Resistance** — auto pivots (gold lines). A long wants to be **at
   support / reclaiming** it; a short **at resistance / rejecting** it.

Volume spike and reward:risk complete a **6-point checklist**. Score **4+ with a
trigger → TAKE IT**; under 4 → wait.

## Install
1. TradingView → **Pine Editor** → paste [`reclaim-playbook.pine`](./reclaim-playbook.pine) → **Add to chart**.
2. Use a **1–5 min** chart of a ride-list name (SPCX / META / AAPL / TSLA).
3. Right-click a ▲/▼ → **Add alert** on the Long/Short confluence condition.

## On the chart
| Element | Meaning |
|---|---|
| Blue / gold lines | 9 EMA / 21 EMA |
| Purple line | VWAP |
| Right-edge histogram + gold dotted line | Volume profile + POC |
| Gold horizontal rays | Support / resistance pivots |
| ▲ LONG / ▼ SHORT | Trigger + 4/6 confluence, VWAP-aligned, outside no-trade |
| △ / ▽ | A raw EMA cross that did **not** clear the checklist |
| Red shaded band | 12–1pm ET — verdict force-locked to NO-TRADE |
| Corner table | Direction, the 6 checks, score, verdict, POC, VWAP, regime, size, R:R |

## Reading the table
It auto-picks the side with more confluence and shows that direction’s six
checks. **VERDICT = TAKE** means: a fresh EMA cross or level reclaim, ≥4/6, on
the right side of VWAP, and not in your no-trade hour. Anything else says WAIT.

## Tuning (settings gear)
- **Volume Profile anchor** — *Session* for intraday balance, *Last swing* to
  measure the current leg only.
- **Profile rows** — more rows = finer POC.
- **Pivot lookback** — higher = fewer, stronger S/R levels.
- **Volume spike ×** and **Min reward:risk** — raise to demand cleaner setups.
- **ADX ≥** — regime cutoff for the TREND/PIN + size read.
- **No-trade window** — HHMM-HHMM in your timezone.

> Signals confirm on **bar close** — read the table on your entry bar, not
> intrabar. Decision support only, not investment advice. Validate on your own
> chart before sizing up.
