# modules/market.py
import math
import yfinance as yf
import streamlit as st

def fmt_number(v, d=2):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:,.{d}f}"
    except Exception:
        return "-"

def fmt_percent(v):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:+.2f}%"
    except Exception:
        return "-"

def fetch_quote(ticker: str):
    # 1) fast_info
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if last and prev: return float(last), float(prev)
    except Exception:
        pass
    # 2) history fallback
    try:
        df = yf.download(ticker, period="7d", interval="1d", auto_adjust=False, progress=False)
        closes = df.get("Close")
        if closes is None or closes.dropna().empty: return None, None
        closes = closes.dropna()
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return last, prev
    except Exception:
        return None, None

TICKER_CSS = """
<style>
.ticker-wrap{overflow:hidden;width:100%;border:1px solid #263042;border-radius:10px;background:#0f1420;}
.ticker-track{display:flex;gap:14px;align-items:center;width:max-content;
  will-change:transform;animation:ticker-scroll var(--speed,30s) linear infinite;}
@keyframes ticker-scroll{0%{transform:translateX(0);}100%{transform:translateX(-50%);}}
.badge{display:inline-flex;align-items:center;gap:8px;background:#0f1420;
  border:1px solid #2b3a55;color:#c7d2fe;padding:6px 10px;border-radius:8px;font-weight:700;white-space:nowrap;}
.badge .name{color:#9fb3c8;font-weight:600;}
.badge .up{color:#e66;} .badge .down{color:#6aa2ff;} .sep{color:#44526b;padding:0 6px;}
</style>
"""

def render_ticker_line(items, speed_sec=30):
    st.markdown(TICKER_CSS, unsafe_allow_html=True)
    chips=[]
    for it in items:
        arrow = "▲" if it["is_up"] else ("▼" if it["is_down"] else "•")
        cls   = "up" if it["is_up"] else ("down" if it["is_down"] else "")
        chips.append(
            f"<span class='badge'><span class='name'>{it['name']}</span>"
            f"{it['last']} <span class='{cls}'>{arrow} {it['pct']}</span></span>"
        )
    line = '<span class="sep">|</span>'.join(chips)
    st.markdown(
        f"<div class='ticker-wrap' style='--speed:{speed_sec}s'>"
        f"<div class='ticker-track'>{line}<span class='sep'>|</span>{line}</div></div>",
        unsafe_allow_html=True
    )

def build_ticker_items():
    rows = [
        ("KOSPI","^KS11",2), ("KOSDAQ","^KQ11",2),
        ("DOW","^DJI",2), ("NASDAQ","^IXIC",2),
        ("USD/KRW","KRW=X",2), ("WTI","CL=F",2),
        ("Gold","GC=F",2), ("Copper","HG=F",3),
    ]
    items=[]
    for name,ticker,dp in rows:
        last, prev = fetch_quote(ticker)
        delta = pct = None
        if last is not None and prev not in (None,0):
            delta = last - prev
            pct = (delta/prev)*100
        items.append({
            "name": name,
            "last": fmt_number(last, dp),
            "pct" : fmt_percent(pct) if pct is not None else "--",
            "is_up": (delta or 0) > 0,
            "is_down": (delta or 0) < 0,
        })
    return items
