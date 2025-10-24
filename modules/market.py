# -*- coding: utf-8 -*-
import math
import streamlit as st
import yfinance as yf

def _fmt_num(v, d=2):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:,.{d}f}"
    except Exception:
        return "-"

def _fmt_pct(v):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:+.2f}%"
    except Exception:
        return "-"

@st.cache_data(ttl=600, show_spinner=False)
def fetch_quote(ticker: str):
    # fast_info → history fallback
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if last and prev:
            return float(last), float(prev)
    except Exception:
        pass
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False)
        c = df["Close"].dropna()
        if c.empty: return None, None
        return float(c.iloc[-1]), float(c.iloc[-2]) if len(c) > 1 else None
    except Exception:
        return None, None

def build_ticker_items():
    rows = [
        ("KOSPI", "^KS11", 2),
        ("KOSDAQ", "^KQ11", 2),
        ("DOW", "^DJI", 2),
        ("NASDAQ", "^IXIC", 2),
        ("USD/KRW", "KRW=X", 2),
        ("WTI", "CL=F", 2),
        ("Gold", "GC=F", 2),
        ("Copper", "HG=F", 3),
    ]
    items = []
    for name, ticker, dp in rows:
        last, prev = fetch_quote(ticker)
        delta = None; pct = None
        if last is not None and prev not in (None, 0):
            delta = last - prev
            pct = (delta / prev) * 100.0
        items.append({
            "name": name,
            "last": _fmt_num(last, dp),
            "pct": _fmt_pct(pct),
            "is_up": (delta or 0) > 0,
            "is_down": (delta or 0) < 0,
        })
    return items

def render_ticker_line(items, speed_sec=30):
    css = """
    <style>
    .ticker-wrap{overflow:hidden;width:100%;border:1px solid #263042;border-radius:10px;background:#0f1420;}
    .ticker-track{display:inline-block;white-space:nowrap;padding:6px 0;
      animation:ticker-scroll var(--speed,30s) linear infinite;}
    @keyframes ticker-scroll {0%{transform:translateX(0);}100%{transform:translateX(-50%);}}
    .badge{display:inline-flex;align-items:center;gap:6px;background:#0f1420;
      border:1px solid #2b3a55;color:#c7d2fe;padding:6px 10px;margin:0 6px;border-radius:8px;font-weight:700;}
    .name{color:#9fb3c8;font-weight:600;} .up{color:#e66;} .down{color:#6aa2ff;} .sep{color:#44526b;padding:0 6px;}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

    chips = []
    for it in items:
        arrow = "▲" if it["is_up"] else ("▼" if it["is_down"] else "•")
        cls = "up" if it["is_up"] else ("down" if it["is_down"] else "")
        chips.append(
            f"<span class='badge'><span class='name'>{it['name']}</span>"
            f"{it['last']} <span class='{cls}'>{arrow} {it['pct']}</span></span>"
        )
    line = "<span class='sep'>|</span>".join(chips)
    st.markdown(
        f"<div class='ticker-wrap' style='--speed:{speed_sec}s'>"
        f"<div class='ticker-track'>{line}<span class='sep'>|</span>{line}</div></div>",
        unsafe_allow_html=True,
    )
