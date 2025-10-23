import streamlit as st
import plotly.express as px
import json, os, time, csv, io
from datetime import datetime
import pytz
from pathlib import Path

st.set_page_config(page_title="AI 뉴스리포트 V26.0 – Web Dashboard", page_icon="📊", layout="wide")
st.markdown("""
<style>
.block-container { padding-top: 1.1rem; padding-bottom: 1.1rem; }
h1, h2, h3 { line-height: 1.25; }
</style>
""", unsafe_allow_html=True)

KST = pytz.timezone("Asia/Seoul")

# ---------- utils ----------
def load_json(path):
    p = Path(path)
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return None

def fmt_mtime(path):
    try:
        ts = os.path.getmtime(path)
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return "-"

def to_float(x):
    try: return float(x)
    except: return None

def normalize_metric(blob):
    """새포맷({'value','pct'})/구포맷(숫자/문자열) 모두 {'value', 'pct'}로 맞춤"""
    if isinstance(blob, dict):
        v = to_float(blob.get("value"))
        pct = blob.get("pct")
        try: pct = float(pct) if pct is not None else None
        except: pct = None
        return {"value": v, "pct": pct}
    else:
        return {"value": to_float(blob), "pct": None}

def fmt_val(x): return "-" if x is None else f"{x:,.2f}"

def reltime(txt):
    try:
        if "T" in txt:
            dt = datetime.strptime(txt[:19], "%Y-%m-%dT%H:%M:%S")
        else:
            dt = datetime.strptime(txt[:25], "%a, %d %b %Y %H:%M:%S")
        dt = KST.localize(dt)
        mins = int((datetime.now(KST)-dt).total_seconds()//60)
        if mins < 1: return "방금 전"
        if mins < 60: return f"{mins}분 전"
        return f"{mins//60}시간 전"
    except: return ""

def dedup_by_title(items, limit=50):
    seen, out = set(), []
    for it in items or []:
        key = (it.get("title") or "").strip().lower()
        if key and key not in seen:
            seen.add(key); out.append(it)
        if len(out) >= limit: break
    return out

def sanitize_kwmap(kmap):
    clean = []
    for k, v in (kmap or {}).items():
        try: n = int(float(v))
        except: continue
        if n > 0: clean.append((k, n))
    clean.sort(key=lambda x: x[1], reverse=True)
    return clean

# ---------- load data ----------
def read_all():
    return (
        load_json("data/market_today.json") or {},
        load_json("data/theme_top5.json") or [],
        load_json("data/keyword_map.json") or {},
        load_json("data/headlines.json") or [],
    )

if "last_reload" not in st.session_state:
    st.session_state.last_reload = time.time()

with st.sidebar:
    st.caption("⚙️ 데이터")
    if st.button("🔄 파일 다시 읽기"): st.session_state.last_reload = time.time()

market, themes, keyword_map, headlines = read_all()

# ---------- header ----------
st.title("📊 AI 뉴스리포트 V26.0 – Web Dashboard Edition")
st.caption("자동 생성형 뉴스·테마·수급 분석 리포트 (실시간 데이터 기반)")
st.caption(f"⏱ 시장지표 갱신: {fmt_mtime('data/market_today.json')} · 헤드라인 갱신: {fmt_mtime('data/headlines.json')} (KST)")

# ---------- sidebar filter/export ----------
with st.sidebar:
    st.markdown("---")
    st.caption("🔎 헤드라인 필터")
    query = st.text_input("키워드 포함", "")
    sources = sorted({(h.get("source") or "").strip() for h in (headlines or []) if h.get("source")})
    sel_sources = st.multiselect("출처 선택(옵션)", sources, default=[])
    st.markdown("---")
    st.caption("⬇️ 내보내기")
    if headlines:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["title","url","source","published"])
        writer.writeheader()
        for h in headlines:
            writer.writerow({
                "title": h.get("title",""), "url": h.get("url",""),
                "source": h.get("source",""), "published": h.get("published","")
            })
        st.download_button("헤드라인 CSV", buf.getvalue().encode("utf-8-sig"),
                           file_name="headlines.csv", mime="text/csv")
        st.download_button("헤드라인 JSON",
                           json.dumps(headlines, ensure_ascii=False, indent=2).encode("utf-8"),
                           file_name="headlines.json", mime="application/json")

# ---------- market ----------
st.header("📉 오늘의 시장 요약")
def draw_metric(col, label, raw, inverse=False):
    m = normalize_metric(raw)
    v = fmt_val(m["value"])
    if m["pct"] is None: col.metric(label, v)
    else:
        sign = "+" if m["pct"] >= 0 else ""
        col.metric(label, v, delta=f"{sign}{m['pct']:.2f}%",
                   delta_color=("inverse" if inverse else "normal"))

c1, c2, c3 = st.columns(3)
draw_metric(c1, "KOSPI",  market.get("KOSPI"),  inverse=False)
draw_metric(c2, "KOSDAQ", market.get("KOSDAQ"), inverse=False)
draw_metric(c3, "환율(USD/KRW)", market.get("USD_KRW"), inverse=True)
if market: st.caption("메모: " + market.get("comment",""))

# ---------- themes ----------
st.header("🔥 TOP 5 테마")
if themes:
    for t in themes:
        st.subheader("📈 " + t.get("name","테마"))
        st.caption(t.get("summary",""))
        st.progress(int(t.get("strength",60)))
        stocks = t.get("stocks", [])
        if stocks: st.caption("대표 종목: " + ", ".join(stocks))
        st.link_button("관련 뉴스 보기", t.get("news_link","https://news.google.com/?hl=ko&gl=KR&ceid=KR:ko"))
        st.divider()
else:
    st.info("테마 데이터가 아직 없습니다. 자동 업데이트 후 표시됩니다.")

# ---------- headlines ----------
st.header("📰 최근 헤드라인 Top 10")
filtered = dedup_by_title(headlines, limit=80)
if query: filtered = [x for x in filtered if query.lower() in (x.get("title","").lower())]
if sel_sources: filtered = [x for x in filtered if (x.get("source") or "").strip() in sel_sources]

if filtered:
    for item in filtered[:10]:
        title = item.get("title","(제목없음)")
        url   = item.get("url","#")
        src   = item.get("source","")
        when  = reltime(item.get("published",""))
        meta  = " · ".join([x for x in [src, when] if x])
        st.markdown(f"- [{title}]({url})  \n  <span style='color:#9aa0a6;font-size:90%'>{meta}</span>", unsafe_allow_html=True)
    with st.expander("더 보기 (11~40)"):
        for item in filtered[10:40]:
            title = item.get("title","(제목없음)")
            url   = item.get("url","#")
            src   = item.get("source","")
            when  = reltime(item.get("published",""))
            meta  = " · ".join([x for x in [src, when] if x])
            st.markdown(f"- [{title}]({url})  \n  <span style='color:#9aa0a6;font-size:90%'>{meta}</span>", unsafe_allow_html=True)
else:
    st.caption("헤드라인 데이터가 아직 없습니다. 자동 업데이트 이후 표시됩니다.")

# ---------- keyword map ----------
st.header("🌍 월간 키워드맵")
items = sanitize_kwmap(keyword_map)[:15]
if items:
    kw, cnt = zip(*items)
    fig = px.bar(x=list(kw), y=list(cnt),
                 labels={"x":"키워드","y":"등장횟수"}, text=list(cnt))
    fig.update_traces(textposition="outside")
    fig.update_layout(xaxis_tickangle=-30, height=420, margin=dict(l=10,r=10,t=10,b=10))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.caption("키워드 데이터가 비어있거나 유효하지 않습니다. 다음 자동 업데이트 후 다시 확인하세요.")            
