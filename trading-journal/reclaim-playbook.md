# The Reclaim Playbook — TradingView indicator

A Pine v5 overlay that reads **four signals together** and scores a **LONG or
SHORT** live on your chart, then blocks your worst hour.

## The four signals
1. **8 / 21 EMA cross** — the trigger. Bull cross (8 over 21) = long trigger,
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

## The strict CALLS / PUTS gate (⑥)
Separate from the 4-of-6 score, there’s a **pure 3-of-3 signal** for your 2-min
entries. A big green **CALLS** label prints below the bar only when **all three
core signals are bullish at once** — 8 > 21 EMA, price above VWAP, and price
above the Volume-Profile POC. A red **PUTS** label prints when all three are
bearish. Each has its own **checkbox** in settings, and its own alert. This is
the “everything is green → go for calls” trigger — nothing prints unless the
whole thesis agrees, so a mixed tape simply shows no label.

- **Mark every aligned bar** (off by default) — on prints a label on every bar
  the three agree; off prints only the *first* bar they line up.
- **Require a fresh EMA cross** (off by default) — on demands the 8/21 cross
  happen on the signal bar, not just that 8 is already above 21.

> The Volume-Profile bias is read on the **live bar**, so CALLS/PUTS labels and
> alerts appear in real time on your entry chart. Add the indicator to the
> **2-min** chart you actually enter on.

## Install
1. TradingView → **Pine Editor** → paste [`reclaim-playbook.pine`](./reclaim-playbook.pine) → **Add to chart**.
2. Use your **2-min** entry chart of a ride-list name (COIN / META / TSLA).
3. Right-click a **CALLS/PUTS** label → **Add alert** → pick the “CALLS — 3 of 3
   bullish” (or PUTS) condition → **Once per bar** → get pinged when it lines up.

## On the chart
| Element | Meaning |
|---|---|
| Blue / gold lines | 8 EMA / 21 EMA |
| Purple line | VWAP |
| Right-edge histogram + gold dotted line | Volume profile + POC |
| Gold horizontal rays | Support / resistance pivots |
| Green **CALLS** / red **PUTS** label | Strict 3-of-3 gate — EMA + VWAP + Profile all agree |
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
