#!/usr/bin/env python3
"""MegaBull paper trading connector (REST, stdlib only).

MegaBull (https://megabull.in) is a free paper trading platform for India.
This connector talks to its public API at https://api.megabull.in. All orders
use virtual money; no real money is ever at risk.

Credentials come from the environment, never from the chat:
  MEGABULL_API_KEY   the key from trade.megabull.in > Profile (valid 1 month)
  MEGABULL_BASE_URL  optional override, default https://api.megabull.in

Instruments are identified by a numeric instrumentToken, not by symbol. The
token list is downloaded from GET /api/marketwatch/instruments and cached at
trader/state/megabull-instruments.csv (refreshed when older than
"instruments_cache_days" from the config, default 7, or with --refresh).
"""
import csv
import datetime
import json
import math
import os
import urllib.error
import urllib.request

BASE_URL = os.getenv("MEGABULL_BASE_URL", "https://api.megabull.in").rstrip("/")
API_KEY = os.getenv("MEGABULL_API_KEY")
CACHE_PATH = os.path.join("trader", "state", "megabull-instruments.csv")
CACHE_DAYS = 7
TIMEOUT = 30


class MegabullError(Exception):
    pass


def _headers():
    if not API_KEY:
        raise MegabullError(
            "MEGABULL_API_KEY is not set. Generate a key at trade.megabull.in > Profile "
            "and set it in the environment (never in the chat). Keys expire after 1 month.")
    return {"api-key": API_KEY, "Accept": "application/json"}


def _request(method, path, body=None):
    """One HTTP call. Returns the decoded JSON body (or raw text for the CSV)."""
    url = BASE_URL + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = _headers()
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(raw)
            msg = "; ".join(err.get("message") or [str(err)])
        except ValueError:
            msg = raw.strip() or str(e.reason)
        raise MegabullError("MegaBull API %s %s failed (%s): %s" % (method, path, e.code, msg))
    except urllib.error.URLError as e:
        raise MegabullError("MegaBull API %s %s unreachable: %s" % (method, path, e.reason))
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return raw


# ---------------------------------------------------------------- instruments

def _cache_age_days(path):
    try:
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return None
    return (datetime.datetime.now() - mtime).total_seconds() / 86400.0


def download_instruments(cache_path=CACHE_PATH):
    """Fetch the instruments CSV via the API and write it to cache_path."""
    meta = _request("GET", "/api/marketwatch/instruments")
    url = meta.get("downloadUrl") if isinstance(meta, dict) else None
    if not url:
        raise MegabullError("the instruments endpoint did not return a downloadUrl: %r" % (meta,))
    req = urllib.request.Request(url, headers={"User-Agent": "day-trader-skill"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise MegabullError("could not download the instruments CSV: %s" % e)
    d = os.path.dirname(cache_path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = cache_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(raw)
    os.replace(tmp, cache_path)
    return cache_path


def ensure_instruments(cache_path=CACHE_PATH, max_age_days=CACHE_DAYS, refresh=False):
    age = _cache_age_days(cache_path)
    if refresh or age is None or age > max_age_days:
        return download_instruments(cache_path)
    return cache_path


def load_instruments(cache_path=CACHE_PATH):
    """[{tradingSymbol, instrumentName, instrumentToken}] from the cached CSV."""
    if not os.path.exists(cache_path):
        raise MegabullError("no instruments cache at %s; run: megabull.py instruments --refresh" % cache_path)
    with open(cache_path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        sym = norm.get("tradingsymbol") or norm.get("trading_symbol") or norm.get("symbol")
        tok = norm.get("instrumenttoken") or norm.get("instrument_token") or norm.get("token")
        name = norm.get("instrumentname") or norm.get("instrument_name") or norm.get("name") or sym
        if sym and tok:
            out.append({"tradingSymbol": sym, "instrumentName": name, "instrumentToken": tok})
    if not out:
        raise MegabullError("the instruments cache at %s has no usable rows; refresh it" % cache_path)
    return out


def normalize_symbol(symbol):
    """HDFCBANK.NS -> HDFCBANK; RELIANCE -> RELIANCE."""
    s = str(symbol or "").strip().upper()
    for suffix in (".NS", ".BO", ".NSE", ".BSE"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s


def resolve_token(symbol, cache_path=CACHE_PATH, refresh=False, max_age_days=CACHE_DAYS):
    """Symbol (Yahoo or plain) -> instrumentToken. Raises MegabullError if unknown."""
    want = normalize_symbol(symbol)
    ensure_instruments(cache_path, max_age_days=max_age_days, refresh=refresh)
    rows = load_instruments(cache_path)
    exact = [r for r in rows if r["tradingSymbol"].upper() == want]
    if exact:
        return exact[0]["instrumentToken"]
    starts = [r for r in rows if r["tradingSymbol"].upper().startswith(want)]
    if len(starts) == 1:
        return starts[0]["instrumentToken"]
    if starts:
        names = ", ".join(sorted(r["tradingSymbol"] for r in starts[:10]))
        raise MegabullError("%s is ambiguous on MegaBull; matches: %s" % (want, names))
    raise MegabullError("%s not found in the MegaBull instruments list; check the symbol or refresh the cache" % want)


# ---------------------------------------------------------------- account

def get_profile():
    return _request("GET", "/api/user/my")


def get_balance():
    """Virtual money summary: total, blocked, left, brokerage per order."""
    p = get_profile()
    return {
        "virtualMoney": p.get("virtualMoney"),
        "virtualMoneyBlocked": p.get("virtualMoneyBlocked"),
        "virtualMoneyLeft": p.get("virtualMoneyLeft"),
        "brokerage": p.get("brokerage"),
        "premiumType": p.get("premiumType"),
    }


def get_positions():
    return _request("GET", "/api/position/my")


def get_holdings():
    return _request("GET", "/api/holding/my")


def get_orders():
    return _request("GET", "/api/order/my")


def get_ltp(instrument_token):
    return _request("GET", "/api/marketwatch/ltp/%s" % instrument_token)


def current_ltp_price(instrument_token):
    """Return a positive current LTP from MegaBull's documented response."""
    data = get_ltp(instrument_token)
    try:
        price = float(data["ltp"])
    except (TypeError, KeyError, ValueError):
        raise MegabullError("MegaBull LTP response has no valid ltp: %r" % (data,))
    if not math.isfinite(price) or price <= 0:
        raise MegabullError("MegaBull returned an invalid LTP: %r" % (data,))
    return price


def get_market_watch():
    return _request("GET", "/api/marketwatch/my")


def get_report_monthly(month, year):
    return _request("GET", "/api/report/monthly/%d/%d" % (int(month), int(year)))


def get_report_virtual(start, end):
    return _request("GET", "/api/report/virtual/%s/%s" % (start, end))


# ---------------------------------------------------------------- orders

ORDER_TYPE_MAP = {"MARKET": "MKT", "MKT": "MKT", "LIMIT": "LIMIT", "SL": "SL", "STOP": "SL", "STOP_LOSS": "SL"}


def build_order_payload(ticket, product="MIS", cache_path=CACHE_PATH, refresh=False, max_age_days=CACHE_DAYS):
    """trader-broker ticket -> MegaBull OrderRequest.

    ticket keys: symbol, qty, side (buy/sell), order_type or type (market/limit/sl),
    price (LIMIT), trigger_price (SL). Bracket legs (stop_loss_stop_price /
    take_profit_limit_price) are NOT sent: MegaBull has no bracket orders, so the
    stop and target are watched by trader-alerts instead.
    """
    symbol = ticket.get("symbol")
    if not symbol:
        raise MegabullError("the ticket has no symbol")
    qty = int(float(ticket.get("qty", 0)))
    if qty <= 0:
        raise MegabullError("quantity must be a positive whole number")
    side = str(ticket.get("side", "")).upper()
    if side not in ("BUY", "SELL"):
        raise MegabullError("side must be buy or sell, got %r" % ticket.get("side"))
    raw_type = str(ticket.get("order_type") or ticket.get("type") or "MARKET").upper()
    order_type = ORDER_TYPE_MAP.get(raw_type)
    if not order_type:
        raise MegabullError("unsupported order type %r (use market, limit or sl)" % raw_type)
    duration = str(ticket.get("product") or ticket.get("duration") or product or "MIS").upper()
    if duration not in ("MIS", "CNC"):
        raise MegabullError("product must be MIS (intraday) or CNC (delivery), got %r" % duration)
    token = ticket.get("instrumentToken") or ticket.get("instrument_token")
    if not token:
        token = resolve_token(symbol, cache_path=cache_path, refresh=refresh, max_age_days=max_age_days)
    payload = {"instrumentToken": str(token), "qty": qty, "type": side,
               "duration": duration, "orderType": order_type}
    if order_type == "LIMIT":
        price = ticket.get("price") or ticket.get("limit_price")
        if price is None or float(price) <= 0:
            raise MegabullError("a LIMIT order needs a positive price")
        payload["price"] = float(price)
    elif order_type == "MKT" and ticket.get("price") is not None:
        price = float(ticket["price"])
        if not math.isfinite(price) or price <= 0:
            raise MegabullError("a market order price, when supplied, must be positive")
        payload["price"] = price
    elif order_type == "SL":
        trigger = ticket.get("trigger_price") or ticket.get("stop_price") or ticket.get("stop_loss_stop_price")
        if trigger is None or float(trigger) <= 0:
            raise MegabullError("an SL order needs a positive trigger_price")
        payload["triggerPrice"] = float(trigger)
        if ticket.get("price") or ticket.get("limit_price"):
            payload["price"] = float(ticket.get("price") or ticket.get("limit_price"))
    return payload


def place_order(ticket, product="MIS", cache_path=CACHE_PATH, refresh=False, max_age_days=CACHE_DAYS):
    payload = build_order_payload(ticket, product=product, cache_path=cache_path,
                                  refresh=refresh, max_age_days=max_age_days)
    if payload["orderType"] == "MKT" and "price" not in payload:
        payload["price"] = current_ltp_price(payload["instrumentToken"])
    return _request("POST", "/api/order/buysell", payload)


def modify_order(order_id, ticket, product="MIS", cache_path=CACHE_PATH, refresh=False, max_age_days=CACHE_DAYS):
    payload = build_order_payload(ticket, product=product, cache_path=cache_path,
                                  refresh=refresh, max_age_days=max_age_days)
    return _request("PUT", "/api/order/buysell/%d" % int(order_id), payload)


def cancel_orders(order_ids):
    ids = [int(i) for i in order_ids]
    if not ids:
        raise MegabullError("no order ids given")
    return _request("PUT", "/api/order/bulk/cancel", ids)


def order_status_by_id(order_id):
    """Find one order in today's orders by id (the API has no single-order GET)."""
    data = get_orders()
    for bucket in ("open", "executed"):
        for o in (data or {}).get(bucket, []) or []:
            if str(o.get("id")) == str(order_id):
                return o
    return None
