"""
Stock / crypto market data for reels — top gainers & losers.
Source: Yahoo Finance public screener endpoints (free, no key).
Markets: US, India (NSE), Crypto.
"""
import urllib.request
import json
import re

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _finology(kind: str, n: int = 5) -> list:
    """India top gainers/losers from finology.in (real Nifty/BSE names)."""
    url = f"https://ticker.finology.in/market/top-{kind}"  # gainers | losers
    req = urllib.request.Request(url, headers=UA)
    html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        txt = re.sub(r"<[^>]+>", " ", row)
        txt = re.sub(r"\s+", " ", txt).strip()
        m = re.match(r"^\d+\s+(.+?)\s+([\d,]+\.\d+)\s+([+-])\s*([\d.]+)\s*%", txt)
        if m:
            name, price, sign, chg = m.groups()
            chg_val = float(chg) * (1 if sign == "+" else -1)
            cur = float(price.replace(",", ""))
            # previous close = current / (1 + change%)
            prev = round(cur / (1 + chg_val / 100), 2) if chg_val != -100 else cur
            sym = name.strip()[:18]
            out.append({"symbol": sym, "name": name.strip()[:24],
                        "change": round(chg_val, 2),
                        "price": cur, "prev": prev, "inr": True})
        if len(out) >= n:
            break
    return out


def _screener(scr_id: str, count: int = 10, region: str = "US",
              lang: str = "en-US") -> list:
    url = ("https://query1.finance.yahoo.com/v1/finance/screener/"
           f"predefined/saved?formatted=true&scrIds={scr_id}&count={count}"
           f"&region={region}&lang={lang}")
    req = urllib.request.Request(url, headers=UA)
    data = json.loads(urllib.request.urlopen(req, timeout=20).read())
    quotes = data["finance"]["result"][0]["quotes"]
    out = []
    def _raw(v):
        return v.get("raw", v) if isinstance(v, dict) else v
    for q in quotes:
        chg = _raw(q.get("regularMarketChangePercent", 0)) or 0
        price = _raw(q.get("regularMarketPrice", 0)) or 0
        prev = _raw(q.get("regularMarketPreviousClose", 0)) or 0
        out.append({
            "symbol": str(q.get("symbol", "")).replace(".NS", ""),
            "name": (q.get("shortName") or q.get("longName") or "")[:24],
            "change": round(float(chg), 2),
            "price": round(float(price), 2),       # current
            "prev": round(float(prev), 2),         # previous close
        })
    return out


def market_news(market: str = "INDIA", n: int = 5) -> list:
    """Top stock-market news headlines (last 1-2 days) via Google News RSS."""
    if market.upper() == "US":
        q = "US+stock+market+dow+nasdaq+sp500+when:1d"
        loc = "hl=en-US&gl=US&ceid=US:en"
    else:
        q = "indian+stock+market+nifty+sensex+when:1d"
        loc = "hl=en-IN&gl=IN&ceid=IN:en"
    url = f"https://news.google.com/rss/search?q={q}&{loc}"
    try:
        req = urllib.request.Request(url, headers=UA)
        xml = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
        titles = re.findall(r"<title>(.*?)</title>", xml)[1:]  # skip feed title
        out = []
        for t in titles:
            t = (t.replace("&amp;", "&").replace("&#39;", "'")
                  .replace("&quot;", '"').replace("&#39;", "'"))
            # strip trailing " - Source"
            t = re.sub(r"\s*-\s*[^-]+$", "", t).strip()
            if t and len(t) > 20:
                out.append(t)
            if len(out) >= n:
                break
        return out
    except Exception:
        return []


def indices(market: str = "INDIA") -> list:
    """Major index levels + day change. market: INDIA | US."""
    if market.upper() == "US":
        syms = [("%5EGSPC", "S&P 500"), ("%5EIXIC", "Nasdaq"),
                ("%5EDJI", "Dow Jones")]
    else:
        syms = [("%5ENSEI", "Nifty 50"), ("%5EBSESN", "Sensex"),
                ("%5ENSEBANK", "Bank Nifty")]
    out = []
    for sym, name in syms:
        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                   "?interval=1d&range=2d")
            req = urllib.request.Request(url, headers=UA)
            d = json.loads(urllib.request.urlopen(req, timeout=15).read())
            meta = d["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice", 0)
            prev = meta.get("chartPreviousClose", meta.get("previousClose", 0))
            chg = ((price - prev) / prev * 100) if prev else 0
            out.append({"name": name, "price": round(price, 0),
                        "change": round(chg, 2),
                        "inr": (market.upper() != "US")})
        except Exception:
            pass
    return out


def market_movers(market: str = "US", n: int = 5) -> dict:
    """
    Return {'gainers': [...], 'losers': [...]} for a market.
    market: US | INDIA | CRYPTO
    """
    market = market.upper()
    if market == "INDIA":
        # finology.in gives real Nifty/BSE names (better than Yahoo screener)
        try:
            gainers = _finology("gainers", n)
            losers = _finology("losers", n)
        except Exception:
            gainers = _screener("day_gainers_in", n, region="IN", lang="en-IN")
            losers = _screener("day_losers_in", n, region="IN", lang="en-IN")
    elif market == "CRYPTO":
        allc = _screener("all_cryptocurrencies_us", n * 4)
        allc = [c for c in allc if "USD" in c["symbol"]]
        allc.sort(key=lambda x: x["change"], reverse=True)
        gainers = allc[:n]
        losers = allc[-n:][::-1]
        for c in gainers + losers:
            c["symbol"] = c["symbol"].replace("-USD", "")
    else:  # US
        gainers = _screener("day_gainers", n)
        losers = _screener("day_losers", n)
    return {"gainers": gainers[:n], "losers": losers[:n]}
