#!/usr/bin/env python3
"""
ai_coach.py — let Claude analyze your trades and write the AI Coach panel.

Reads the journal's data.js, computes a compact statistical profile of your
trading (win rate, payoff math, edge by hour/weekday/size, post-loss tilt,
rule-based what-if P&L), sends it to the Claude API, and writes coach.js — the
file the journal renders as its "AI Coach" card. Re-run any time to refresh.

    pip install anthropic
    export ANTHROPIC_API_KEY=...        # or: ant auth login
    python ai_coach.py

Only aggregate statistics are sent to the API — not your account number.
Figures are informational only, not tax or investment advice.
"""
import os
import re
import sys
import json
import datetime as dt
from collections import defaultdict
from zoneinfo import ZoneInfo

try:
    import anthropic
except ImportError:
    sys.exit("Missing dependency. Run:  pip install anthropic")

HERE = os.path.dirname(os.path.abspath(__file__))
ET = ZoneInfo("America/New_York")
MODEL = os.environ.get("COACH_MODEL", "claude-opus-5")


# --------------------------------------------------------------------------- #
# load trades from data.js
# --------------------------------------------------------------------------- #
def load_trades():
    raw = open(os.path.join(HERE, "data.js")).read()
    blob = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    return blob["trades"]


def et_parts(iso):
    d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET)
    return d.hour, d.strftime("%a")


# --------------------------------------------------------------------------- #
# compute the statistical profile the model reasons over
# --------------------------------------------------------------------------- #
def profile(trades):
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    gross = sum(t["pnl"] for t in trades)
    win_sum = sum(t["pnl"] for t in wins)
    loss_sum = sum(t["pnl"] for t in losses)
    avg_win = win_sum / len(wins) if wins else 0
    avg_loss = loss_sum / len(losses) if losses else 0
    breakeven = abs(avg_loss) / (avg_win + abs(avg_loss)) if (avg_win + abs(avg_loss)) else 0

    by_hour, by_dow, by_sym, by_size = (defaultdict(lambda: [0, 0, 0]) for _ in range(4))
    for t in trades:
        h, dow = et_parts(t["t"])
        for bucket, key in ((by_hour, h), (by_dow, dow), (by_sym, t["symbol"]),
                            (by_size, min(int(t["qty"]) if t["qty"] >= 1 else 0, 10))):
            bucket[key][0] += t["pnl"]; bucket[key][1] += 1
            if t["pnl"] > 0:
                bucket[key][2] += 1

    after_loss = [trades[i]["pnl"] for i in range(1, n) if trades[i - 1]["pnl"] < 0]
    after_win = [trades[i]["pnl"] for i in range(1, n) if trades[i - 1]["pnl"] > 0]

    def scenario(skip_mid=False, skip_late=False, no_postloss=False, cap=None):
        tot = 0.0
        for i, t in enumerate(trades):
            h, dow = et_parts(t["t"])
            if skip_mid and h in (12, 13):
                continue
            if skip_late and dow in ("Thu", "Fri"):
                continue
            if no_postloss and i > 0 and trades[i - 1]["pnl"] < 0:
                continue
            p = t["pnl"]
            if cap and t["qty"] > cap:
                p *= cap / t["qty"]
            tot += p
        return round(tot, 2)

    fmt = lambda d: {str(k): {"pnl": round(v[0], 2), "n": v[1], "win_pct": round(v[2] / v[1] * 100)}
                     for k, v in sorted(d.items())}
    return {
        "trades": n, "net_pnl": round(gross, 2),
        "win_rate_pct": round(len(wins) / n * 100, 1) if n else 0,
        "breakeven_win_rate_pct": round(breakeven * 100, 1),
        "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
        "profit_factor": round(win_sum / abs(loss_sum), 2) if loss_sum else None,
        "pnl_after_a_loss": round(sum(after_loss) / len(after_loss), 2) if after_loss else None,
        "pnl_after_a_win": round(sum(after_win) / len(after_win), 2) if after_win else None,
        "by_hour_et": fmt(by_hour), "by_weekday": fmt(by_dow),
        "by_symbol": fmt(by_sym), "by_size_contracts": fmt(by_size),
        "whatif_net": {
            "baseline": scenario(),
            "skip_midday_12_1pm": scenario(skip_mid=True),
            "skip_thu_fri": scenario(skip_late=True),
            "no_trade_after_loss": scenario(no_postloss=True),
            "cap_size_3": scenario(cap=3),
            "midday_plus_cap3": scenario(skip_mid=True, cap=3),
        },
    }


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["grade", "verdict", "leaks", "plan", "strengths", "note"],
    "properties": {
        "grade": {"type": "string"},
        "verdict": {"type": "string"},
        "leaks": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                  "required": ["title", "html"], "properties": {"title": {"type": "string"}, "html": {"type": "string"}}}},
        "plan": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                 "required": ["title", "html"], "properties": {"title": {"type": "string"}, "html": {"type": "string"}}}},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "note": {"type": "string"},
    },
}

PROMPT = """You are a trading coach reviewing a day-trader's realized-trade statistics.
Below is a JSON profile of their entire trade history (aggregates only).

Write a candid, specific, encouraging coaching analysis. Ground EVERY claim in the
numbers — cite exact figures. Focus on the largest, most fixable leaks and give a
concrete, ordered plan. Wrap the single most impactful phrase of each leak/plan item
in <span class='impact'>…</span> (e.g. an expected dollar improvement). You may use
<b> for emphasis. Keep each item to 1–2 sentences.

Return 3–4 leaks (biggest money-losers first), a 4–5 step 30-day plan, 2–3 genuine
strengths, a one-line note, a short `verdict` paragraph, and a `grade` (a short phrase
like "Breakeven — fixable"). This is behavioral analysis of the user's own data, not
investment advice.

PROFILE:
%s"""


def main():
    trades = load_trades()
    if not trades:
        sys.exit("No trades in data.js — run import_robinhood.py first.")
    prof = profile(trades)
    print(f"Analyzing {prof['trades']} trades (net ${prof['net_pnl']:,.2f})…")

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": PROMPT % json.dumps(prof, indent=2)}],
    )
    if resp.stop_reason == "refusal":
        sys.exit("Model declined to analyze this request.")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    coach = json.loads(text)
    coach["generatedAt"] = dt.date.today().isoformat()
    coach["model"] = resp.model

    out = ("/* AI Coach analysis — generated by ai_coach.py via the Claude API.\n"
           "   Figures are informational only, not tax or investment advice. */\n"
           "window.COACH = " + json.dumps(coach, indent=2) + ";\n")
    with open(os.path.join(HERE, "coach.js"), "w") as f:
        f.write(out)
    print(f"Wrote coach.js — grade: {coach.get('grade')}. Reload the journal.")


if __name__ == "__main__":
    main()
