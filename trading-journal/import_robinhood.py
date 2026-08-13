#!/usr/bin/env python3
"""
import_robinhood.py — plug the journal into your Robinhood account.

Logs into Robinhood, pulls your filled stock + option orders, reconstructs
closed round-trip trades (FIFO) with realized P&L, downloads the underlying
price history for every symbol you traded, and writes `data.js` — the single
file the journal (index.html) reads. Re-run any time to refresh.

    pip install robin_stocks
    python import_robinhood.py            # prompts for login (+ MFA)

Credentials are read from env vars if present, else prompted:
    RH_USERNAME, RH_PASSWORD, RH_MFA (optional TOTP code)

Nothing is stored except the generated data.js (your trades + prices).
Figures are informational only — not tax or investment advice.
"""
import os
import sys
import json
import getpass
import datetime as dt
from collections import defaultdict, deque

try:
    import robin_stocks.robinhood as rh
except ImportError:
    sys.exit("Missing dependency. Run:  pip install robin_stocks")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data.js")
LOOKBACK_DAYS = 400  # how far back to pull price history


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
def login():
    user = os.environ.get("RH_USERNAME") or input("Robinhood email: ")
    pw = os.environ.get("RH_PASSWORD") or getpass.getpass("Password: ")
    mfa = os.environ.get("RH_MFA")
    kwargs = {"username": user, "password": pw, "store_session": True}
    if mfa:
        kwargs["mfa_code"] = mfa
    rh.login(**kwargs)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def iso(ts):
    """Normalize Robinhood timestamps to 'YYYY-MM-DDTHH:MM:SSZ'."""
    if not ts:
        return None
    return ts.split(".")[0].replace("+00:00", "") + "Z" if "T" in ts else ts


# --------------------------------------------------------------------------- #
# stock round-trips (FIFO)
# --------------------------------------------------------------------------- #
def stock_trades():
    trades = []
    orders = rh.orders.get_all_stock_orders() or []
    # oldest first, only filled
    fills = []
    for o in orders:
        if o.get("state") != "filled":
            continue
        try:
            sym = rh.stocks.get_symbol_by_url(o["instrument"])
        except Exception:
            sym = o.get("symbol", "?")
        qty = f(o.get("cumulative_quantity"))
        price = f(o.get("average_price"))
        if qty <= 0 or price <= 0:
            continue
        fills.append({
            "t": iso(o.get("last_transaction_at") or o.get("updated_at")),
            "symbol": sym,
            "side": o.get("side"),
            "qty": qty,
            "price": price,
        })
    fills.sort(key=lambda x: x["t"] or "")

    lots = defaultdict(deque)  # symbol -> deque of (qty, price)
    for fl in fills:
        sym = fl["symbol"]
        if fl["side"] == "buy":
            lots[sym].append([fl["qty"], fl["price"]])
        else:  # sell -> realize against FIFO lots
            remaining = fl["qty"]
            realized = 0.0
            while remaining > 1e-9 and lots[sym]:
                lot = lots[sym][0]
                take = min(remaining, lot[0])
                realized += take * (fl["price"] - lot[1])
                lot[0] -= take
                remaining -= take
                if lot[0] <= 1e-9:
                    lots[sym].popleft()
            if fl["qty"] > 0:
                trades.append({
                    "t": fl["t"], "date": (fl["t"] or "")[:10], "symbol": sym,
                    "qty": round(fl["qty"], 4), "price": round(fl["price"], 2),
                    "pnl": round(realized, 2), "kind": "equity",
                })
    return trades


# --------------------------------------------------------------------------- #
# option round-trips (FIFO per contract)
# --------------------------------------------------------------------------- #
def option_trades():
    trades = []
    orders = rh.orders.get_all_option_orders() or []
    fills = []
    for o in orders:
        if o.get("state") != "filled":
            continue
        sym = o.get("chain_symbol", "?")
        for leg in o.get("legs", []):
            key = f"{sym}|{leg.get('strike_price')}|{leg.get('expiration_date')}|{leg.get('option_type')}"
            for ex in leg.get("executions", []):
                qty = f(ex.get("quantity"))
                price = f(ex.get("price"))
                if qty <= 0:
                    continue
                # position_effect: 'open' or 'close'
                fills.append({
                    "t": iso(ex.get("timestamp") or o.get("updated_at")),
                    "symbol": sym, "key": key,
                    "effect": leg.get("position_effect"),
                    "side": leg.get("side"),
                    "qty": qty, "price": price,
                })
    fills.sort(key=lambda x: x["t"] or "")

    lots = defaultdict(deque)
    for fl in fills:
        k = fl["key"]
        if fl["effect"] == "open":
            # signed cost per contract; long call/put = debit
            sign = 1 if fl["side"] == "buy" else -1
            lots[k].append([fl["qty"], fl["price"], sign])
        else:  # close
            remaining = fl["qty"]
            realized = 0.0
            while remaining > 1e-9 and lots[k]:
                lot = lots[k][0]
                take = min(remaining, lot[0])
                # long: (close-open)*100 ; short: (open-close)*100
                realized += take * (fl["price"] - lot[1]) * lot[2] * 100
                lot[0] -= take
                remaining -= take
                if lot[0] <= 1e-9:
                    lots[k].popleft()
            trades.append({
                "t": fl["t"], "date": (fl["t"] or "")[:10], "symbol": fl["symbol"],
                "qty": round(fl["qty"], 4), "price": round(fl["price"] * 100, 2),
                "pnl": round(realized, 2), "kind": "option",
            })
    return trades


# --------------------------------------------------------------------------- #
# prices
# --------------------------------------------------------------------------- #
def prices_for(symbols):
    prices = {}
    for sym in sorted(symbols):
        try:
            hist = rh.stocks.get_stock_historicals(sym, interval="day", span="year")
        except Exception:
            continue
        series = []
        for b in hist or []:
            if not b.get("close_price"):
                continue
            series.append([
                b["begins_at"][:10],
                round(f(b["open_price"]), 2),
                round(f(b["high_price"]), 2),
                round(f(b["low_price"]), 2),
                round(f(b["close_price"]), 2),
            ])
        if series:
            prices[sym] = series
    return prices


def spy_intraday(day):
    try:
        hist = rh.stocks.get_stock_historicals("SPY", interval="5minute", span="day")
    except Exception:
        return []
    bars = []
    for b in hist or []:
        if not b.get("close_price") or not b["begins_at"].startswith(day):
            continue
        bars.append({
            "t": iso(b["begins_at"]),
            "o": round(f(b["open_price"]), 2), "h": round(f(b["high_price"]), 2),
            "l": round(f(b["low_price"]), 2), "c": round(f(b["close_price"]), 2),
        })
    return bars


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    print("Logging into Robinhood…")
    login()
    print("Pulling orders…")
    trades = stock_trades() + option_trades()
    trades = [t for t in trades if t["t"]]
    trades.sort(key=lambda x: x["t"])
    if not trades:
        sys.exit("No filled trades found.")

    symbols = {t["symbol"] for t in trades}
    print(f"Found {len(trades)} closed trades across {len(symbols)} symbols. Fetching prices…")
    prices = prices_for(symbols)
    intraday_day = trades[-1]["date"]
    intraday = spy_intraday(intraday_day) if "SPY" in symbols else []

    try:
        acct = rh.profiles.load_account_profile().get("account_number", "")
    except Exception:
        acct = ""
    masked = "•••" + acct[-4:] if acct else "—"

    meta = {
        "account": masked,
        "generatedAt": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rangeStart": trades[0]["date"],
        "rangeEnd": trades[-1]["date"],
        "tradeCount": len(trades),
        "totalPnl": round(sum(t["pnl"] for t in trades), 2),
        "symbolsTraded": sorted(symbols),
        "chartableSymbols": sorted(s for s in symbols if s in prices),
        "intradayDate": intraday_day,
    }
    blob = {"meta": meta, "trades": trades, "prices": prices, "intraday": intraday}
    with open(OUT, "w") as fh:
        fh.write("window.JOURNAL_DATA = " + json.dumps(blob, separators=(",", ":")) + ";\n")

    print(f"Wrote {OUT}")
    print(f"  {len(trades)} trades · net realized ${meta['totalPnl']:,.2f} "
          f"· {meta['rangeStart']} → {meta['rangeEnd']}")
    print("Open index.html to view your journal.")
    rh.logout()


if __name__ == "__main__":
    main()
