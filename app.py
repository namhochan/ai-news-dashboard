import json, os
import streamlit as st
import pandas as pd
import plotly.express as px

DATA_DIR = "data"
def load_json(n,d=None):
    p=os.path.join(DATA_DIR,n)
    if not os.path.exists(p):return d
    with open(p,"r",encoding="utf-8") as f:return json.load(f)

st.set_page_config(page_title="AI 뉴스 대시보드 V27",layout="wide")
st.title("📊 AI 뉴스 대시보드 V27 – 자동 업데이트형")

m=load_json("market_today.json",{})
st.caption(f"마지막 갱신: {m.get('updated_at','-')}")

c1,c2,c3=st.columns(3)
def show(c,t,d):
    with c:
        if not d or d.get("value") is None:
            st.metric(t,"-",delta="데이터 없음")
        else:
            st.metric(t,f"{d['value']:,}",delta=f"{d['dir']}{d['change_pct']}%")
show(c1,"KOSPI",m.get("KOSPI",{}))
show(c2,"KOSDAQ",m.get("KOSDAQ",{}))
show(c3,"환율(USD/KRW)",m.get("USDKRW",{}))

st.markdown("---")
st.subheader("🔥 TOP 5 테마")
t5=load_json("theme_top5.json",[])
if t5:
    for t in t5:
        st.markdown(f"**{t.get('theme',t.get('keyword'))}** — 뉴스 빈도 {t.get('score',t.get('count'))}")
else:
    st.info("데이터 없음")

st.markdown("---")
st.subheader("🗞️ 최신 헤드라인 Top 10")
h=load_json("recent_headlines.json",[])
if h:
    for i in h[:10]:
        st.markdown(f"- [{i['title']}]({i['url']})")
else:
    st.info("헤드라인 없음")

st.markdown("---")
st.subheader("🌍 월간 키워드맵")
kw=load_json("keyword_map.json",[])
if kw:
    df=pd.DataFrame(kw)
    fig=px.bar(df,x="keyword",y="count",text="count")
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig,use_container_width=True)
else:
    st.info("키워드 없음")
