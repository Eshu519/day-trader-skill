"""Remap the US (NYSE) test fixtures to NSE times.

NYSE session 9:30-16:00 ET (78 5-min bars) -> NSE session 09:15-15:30 IST (75 bars).
Bar i in NYSE maps to bar i in NSE; slots >= 75 are dropped. Daily bars (13:30 UTC)
map to 03:45 UTC (09:15 IST) on the same date. regularMarketTime is remapped the same
way. Meta timezone fields are set to IST.
"""
import gzip
import json
import datetime
import os
import shutil

EPOCH = datetime.datetime(1970, 1, 1)


def eastern_offset(utc):
    """Old US DST rule, used only to read the fixture's NYSE wall-clock times."""
    def nth_sunday(year, month, n):
        d = datetime.date(year, month, 1)
        d += datetime.timedelta(days=(6 - d.weekday()) % 7)
        return d + datetime.timedelta(weeks=n - 1)
    y = utc.year
    start = datetime.datetime.combine(nth_sunday(y, 3, 2), datetime.time(7, 0))
    end = datetime.datetime.combine(nth_sunday(y, 11, 1), datetime.time(6, 0))
    naive = utc.replace(tzinfo=None)
    return -4 if start <= naive < end else -5


def nyse_to_nse_ts(ts):
    """Unix seconds (NYSE bar) -> unix seconds (NSE bar, same slot index)."""
    utc = EPOCH + datetime.timedelta(seconds=int(ts))
    local = utc + datetime.timedelta(hours=eastern_offset(utc))
    open_dt = datetime.datetime.combine(local.date(), datetime.time(9, 30))
    delta = local - open_dt
    slot = delta.total_seconds() / 300.0
    if slot >= 75:
        return None
    nse_local = datetime.datetime.combine(local.date(), datetime.time(9, 15)) + delta
    return int((nse_local - datetime.timedelta(hours=5, minutes=30) - EPOCH).total_seconds())


def nyse_to_nse_daily_ts(ts):
    """Daily bar at 13:30/14:30 UTC -> 03:45 UTC (09:15 IST) same date."""
    utc = EPOCH + datetime.timedelta(seconds=int(ts))
    local = utc + datetime.timedelta(hours=eastern_offset(utc))
    nse_local = datetime.datetime.combine(local.date(), datetime.time(9, 15))
    return int((nse_local - datetime.timedelta(hours=5, minutes=30) - EPOCH).total_seconds())


def remap_meta(meta):
    if not isinstance(meta, dict):
        return
    meta["timezone"] = "IST"
    meta["exchangeTimezoneName"] = "Asia/Kolkata"
    meta["gmtoffset"] = 19800
    rmt = meta.get("regularMarketTime")
    if isinstance(rmt, (int, float)):
        meta["regularMarketTime"] = nyse_to_nse_ts(rmt) if _is_intraday(rmt) else nyse_to_nse_daily_ts(rmt)
    # drop the US trading-period blocks; the code never reads them
    meta.pop("currentTradingPeriod", None)
    meta.pop("tradingPeriods", None)


def _is_intraday(ts):
    utc = EPOCH + datetime.timedelta(seconds=int(ts))
    local = utc + datetime.timedelta(hours=eastern_offset(utc))
    return local.time() != datetime.time(9, 30) or True  # intraday fixtures are all 5m/1m bars


def remap_chart_result(r, daily=False):
    ts = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0] or {}
    keep = []
    new_ts = []
    for i, t in enumerate(ts):
        nt = nyse_to_nse_daily_ts(t) if daily else nyse_to_nse_ts(t)
        if nt is None:
            continue
        keep.append(i)
        new_ts.append(nt)
    r["timestamp"] = new_ts
    for k, col in list(q.items()):
        if isinstance(col, list) and len(col) == len(ts):
            q[k] = [col[i] for i in keep]
    # adjclose lives alongside quote in some fixtures
    adj = ((r.get("indicators") or {}).get("adjclose") or [{}])[0] or {}
    for k, col in list(adj.items()):
        if isinstance(col, list) and len(col) == len(ts):
            adj[k] = [col[i] for i in keep]
    remap_meta(r.get("meta") or {})


def convert_chart_file(path, daily=False, gz=False):
    if gz:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
    else:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    for r in doc.get("chart", {}).get("result") or []:
        remap_chart_result(r, daily=daily)
    if gz:
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(doc, fh, separators=(",", ":"))
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, separators=(",", ":"))
    print("converted", path)


def convert_spark_file(path, daily=False):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    for s in doc.get("spark", {}).get("result") or []:
        for resp in s.get("response") or []:
            remap_chart_result(resp, daily=daily)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    print("converted", path)


def convert_wall5m(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        doc = json.load(fh)
    for sym, payload in doc.items():
        for r in payload.get("chart", {}).get("result") or []:
            remap_chart_result(r, daily=False)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    print("converted", path)


FIX = "tests/fixtures"
convert_chart_file(os.path.join(FIX, "trader-entry", "TSLA-2026-10-19-5m.json"))
convert_chart_file(os.path.join(FIX, "trader-entry", "DEMO-1m-synthetic.json"))
convert_chart_file(os.path.join(FIX, "trader-news", "chart-TSLA.json"))
convert_chart_file(os.path.join(FIX, "trader-timemachine", "TSLA-60d5m.json.gz"), gz=True)
convert_chart_file(os.path.join(FIX, "trader-scanner", "TSLA-5m-live-2026-10-20-1001.json"))
convert_spark_file(os.path.join(FIX, "trader-scanner", "spark-5m-live-2026-10-20-1001.json"))
convert_spark_file(os.path.join(FIX, "trader-scanner", "spark-3mo-live-2026-10-20.json"), daily=True)
convert_spark_file(os.path.join(FIX, "trader-scanner", "daily-spark-2026-10-19.json"), daily=True)
convert_wall5m(os.path.join(FIX, "trader-scanner", "wall5m-2026-10-19.json.gz"))
